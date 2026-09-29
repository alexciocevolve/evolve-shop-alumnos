import secrets
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.orm import Session, joinedload, selectinload

from app import payments
from app.models import (
    Address,
    Cart,
    CartItem,
    Category,
    Order,
    OrderItem,
    Product,
    ProductPriceHistory,
    User,
    UserSession,
)
from app.observability import fingerprint, log
from app.schemas import AddressIn
from app.security import DUMMY_HASH, hash_password, verify_password


def list_categories(db: Session) -> list[Category]:
    # Ordered by name so the buttons on screen never change places between page loads.
    return list(db.scalars(select(Category).order_by(Category.name)))


def get_product(db: Session, product_id: int) -> Product | None:
    return db.get(Product, product_id)  # None when there is no such row


def list_products(
    db: Session, category: str | None, cursor: int, limit: int
) -> tuple[list[Product], int | None]:
    # Keyset pagination: "give me the rows AFTER the last one I saw" (id > cursor).
    # Unlike OFFSET, the database jumps straight to that point through the primary-key
    # index, and rows inserted meanwhile can never shift a page or repeat an item.
    query = select(Product).where(Product.id > cursor)

    # The filter still arrives as a name ("laptops"), because that is what the address bar
    # shows and what the API promised; the category now lives in its own table, so reaching
    # the name means joining. The caller never notices that the schema changed.
    if category is not None:
        query = query.join(Product.category).where(Category.name == category)

    # Every product is about to be asked for its category name. Without this line SQLAlchemy
    # would fetch each one with its own SELECT: 1 query for the page plus 1 per product
    # (the "N+1 queries" problem). joinedload brings them in the same query.
    query = query.options(joinedload(Product.category))

    # Ask for one row more than the page size: if it arrives, there is a next page,
    # and we know it without running a second query.
    rows = list(db.scalars(query.order_by(Product.id).limit(limit + 1)))
    if len(rows) > limit:
        page = rows[:limit]
        return page, page[-1].id
    return rows, None


def list_price_history(db: Session, product_id: int) -> list[ProductPriceHistory] | None:
    # The return type carries the decision: None when there is no such product, an empty
    # list when the product exists and its price has never changed. They are two different
    # situations and they get two different answers - a route that received [] for both
    # could not tell them apart, and would end up saying "this product has never changed
    # price" about a product that does not exist.
    #
    # Looking the product up costs one extra query. The cheap version - query the history
    # table and return whatever comes back - is one query and the wrong answer, because for
    # product 999 it answers []. The query is spent on purpose, to keep the distinction.
    if db.get(Product, product_id) is None:
        return None

    return list(
        db.scalars(
            select(ProductPriceHistory)
            .where(ProductPriceHistory.product_id == product_id)
            .order_by(ProductPriceHistory.changed_at, ProductPriceHistory.id)
        )
    )
    # Oldest first, because a history is read forwards. The id is a tie-breaker and not
    # decoration: changed_at defaults to now(), which in PostgreSQL is the start of the
    # TRANSACTION, so two price changes committed together carry the exact same timestamp.
    # Ordering by the date alone would leave their order up to the database.


def create_cart(db: Session) -> Cart:
    # 32 random bytes, not a number anyone can guess or count up from.
    cart = Cart(token=secrets.token_urlsafe(32))
    db.add(cart)
    db.commit()
    return cart


def get_cart(db: Session, token: str) -> Cart | None:
    # The lines and their products are loaded up front: every caller is about to read the
    # name and the price of each one, and doing it lazily would be one query per line.
    return db.scalars(
        select(Cart)
        .where(Cart.token == token)
        .options(selectinload(Cart.items).joinedload(CartItem.product))
    ).first()


def set_cart_item(db: Session, cart: Cart, product_id: int, quantity: int) -> Cart | None:
    product = db.get(Product, product_id)
    if product is None:
        return None  # no such product; the route turns this into a 404

    # An immediate answer for the shopper. It is NOT the check that counts: stock can run
    # out between now and the checkout, so create_order checks again with the rows locked.
    if quantity > product.stock:
        raise ValueError(
            f"Insufficient stock for {product.name}: "
            f"{product.stock} left, {quantity} requested"
        )

    # One statement that inserts the line or, if this product is already in this cart,
    # overwrites its quantity. That is what makes PUT idempotent: sending it twice by
    # accident leaves the cart exactly as sending it once.
    db.execute(
        postgres_insert(CartItem)
        .values(cart_token=cart.token, product_id=product_id, quantity=quantity)
        .on_conflict_do_update(
            index_elements=[CartItem.cart_token, CartItem.product_id],
            set_={"quantity": quantity},
        )
    )
    db.commit()
    return get_cart(db, cart.token)  # read back, so the caller gets the lines as they are now


def remove_cart_item(db: Session, cart: Cart, product_id: int) -> bool:
    result = db.execute(
        delete(CartItem).where(
            CartItem.cart_token == cart.token, CartItem.product_id == product_id
        )
    )
    db.commit()
    # False when the product was not in the cart: nothing was deleted. That is a different
    # situation from a successful delete, and the route answers it differently.
    return result.rowcount > 0


def cart_total_cents(cart: Cart) -> int:
    # Today's price, read from products. Nothing about money comes from the client.
    return sum(item.product.price_cents * item.quantity for item in cart.items)


def create_order(db: Session, cart: Cart, user: User) -> Order:
    # The whole thing is ONE transaction: everything below happens, or nothing does.
    #
    # And no network call happens inside it any more, which is a real improvement that came
    # for free. Objective 16 charged the card right here, holding SELECT ... FOR UPDATE on
    # the products while Stripe thought about it - the shop's locks were hostage to somebody
    # else's latency. Now creating the order and paying for it are two acts, so the
    # transaction closes before anybody talks to Stripe.
    #
    # What it costs: the order now exists WITHOUT BEING PAID. That is the whole objective.
    if not cart.items:
        raise ValueError("The cart is empty")

    # Where this is going. Read from the server, never sent by the browser: a client that
    # could name an address id would be a client that could name somebody else's.
    shipping_address = get_active_address(db, user, is_billing=False)
    if shipping_address is None:
        # An order has to know where it goes. The screen says so before the button is
        # pressed, and this is the check that holds whoever skips the screen.
        raise ValueError("A shipping address is required before placing an order")

    # Lock the product rows until this transaction finishes, so that two people going for
    # the last unit at the same time cannot both pass the check below (session 14).
    # ORDER BY id makes every checkout take its locks in the same order, which is what
    # stops two of them from deadlocking each other; populate_existing makes sure the
    # objects hold the values just read under the lock and not something loaded earlier.
    products = {
        product.id: product
        for product in db.scalars(
            select(Product)
            .where(Product.id.in_([item.product_id for item in cart.items]))
            .order_by(Product.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }

    # Check EVERY line before touching anything. One line short of stock and the order
    # does not happen at all: no stock moved, nothing half-done to clean up afterwards.
    for item in cart.items:
        product = products[item.product_id]
        if item.quantity > product.stock:
            raise ValueError(
                f"Insufficient stock for {product.name}: "
                f"{product.stock} left, {item.quantity} requested"
            )

    # Only now that every line is known to be servable.
    order = Order(
        user_id=user.id,
        # The email as it was on the day of the order, not a live reading of the account.
        # Frozen for the same reason as the price and the address: changing the account
        # email next year must not rewrite where this order was confirmed to.
        customer_email=user.email,
        # The row, not a copy of its lines. Safe because the row will never change: the
        # order keeps the address it was sent to even after the person moves.
        shipping_address_id=shipping_address.id,
        # The total is added up here, on the server, from prices the server read itself.
        total_cents=sum(
            products[item.product_id].price_cents * item.quantity for item in cart.items
        ),
        items=[
            OrderItem(
                product_id=item.product_id,
                quantity=item.quantity,
                # Today's price, frozen. This is the column cart_items does not have.
                price_cents=products[item.product_id].price_cents,
            )
            for item in cart.items
        ],
    )
    for item in cart.items:
        products[item.product_id].stock -= item.quantity

    db.add(order)
    db.delete(cart)  # the lines go with it, and the cart has served its purpose
    db.commit()
    return order


def start_checkout(db: Session, order: Order, gateway) -> str:
    """Hand the order over to Stripe and return where to send the buyer.

    Separate from create_order on purpose, and not just for tidiness: they are now two
    different acts with a gap between them that the shop does not control. The order exists
    at the end of the first one and nobody has paid; the second one only opens a door.

    The lines go over as REAL line items, which the previous design could not do - a
    PaymentIntent takes one number. So the product names and quantities appear on Stripe's
    page and on the receipt, which is what a buyer needs to recognise what they are paying
    for.
    """
    lines = [
        {
            "price_data": {
                "currency": payments.CURRENCY,
                "product_data": {"name": item.product.name},
                # The price FROZEN on the order, not today's catalogue price. If somebody
                # edits the product while this customer is typing their card, they still
                # pay what they were shown.
                "unit_amount": item.price_cents,
            },
            "quantity": item.quantity,
        }
        for item in order.items
    ]
    # The order is already committed, so if Stripe fails here the order stays behind,
    # pending, with no way to pay for it. Read now, for the log lines below.
    who = {"user.id": order.user_id, "shop.order_id": order.id, "shop.amount_cents": order.total_cents}
    started = time.perf_counter()
    try:
        checkout = gateway.start(
            order_id=order.id, lines=lines, customer_email=order.customer_email
        )
    except Exception as e:
        log.error(
            "checkout could not start",
            extra={
                "event.action": "checkout.start",
                "event.outcome": "failure",
                "event.duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "error.type": type(e).__name__,
                "error.message": str(e),
                **who,
            },
        )
        raise
    order.checkout_session_id = checkout.session_id
    db.commit()

    # Nothing has been charged yet: this is the door opening, not the money moving. What
    # happens next is on Stripe's page, which this shop cannot see. That is why the line
    # carries the session id: it is the thread that joins this order to whatever Stripe
    # says later, and to the order.confirm line if the buyer ever comes back.
    log.info(
        f"checkout started for order {order.id}",
        extra={
            "event.action": "checkout.start",
            "event.outcome": "success",
            # Only creating the page, but it still happens while the buyer waits for it.
            "event.duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "shop.checkout_session_id": checkout.session_id,
            "shop.checkout_lines": len(lines),
            **who,
        },
    )
    return checkout.url


def confirm_order(db: Session, order: Order) -> Order:
    """Mark the order paid because the browser came back saying so.

    READ THIS BEFORE COPYING IT. It believes whoever calls it, and that is wrong in two
    ways that the next objective demonstrates rather than argues:

      · Anyone can call it. It checks nothing against Stripe, so a `curl` buys goods.
      · It only runs if the buyer comes back. Close the tab after paying and the money is
        gone and the order stays pending, with nobody to notice.

    It is written this way deliberately, because it is what almost every first integration
    does, and because Stripe itself warns against it in the same page that explains how:
    "Activar la gestion logistica solo desde tu pagina de exito de Checkout no es fiable."
    That sentence is worth reading AFTER having seen it break, not before.
    """
    previous_status = order.status
    order.status = "paid"
    db.commit()

    # Logged with the one field that gives this function away. Every confirmation today
    # says verified_with_stripe: false, because nothing asked Stripe; in Kibana that is a
    # column that should never be false on a paid order, and here it always is.
    log.info(
        f"order {order.id} marked paid",
        extra={
            "event.action": "order.confirm",
            "user.id": order.user_id,
            "shop.order_id": order.id,
            "shop.previous_status": previous_status,
            "shop.checkout_session_id": order.checkout_session_id,
            "shop.verified_with_stripe": False,
        },
    )
    return order


def list_orders(db: Session, user: User) -> list[Order]:
    return list(
        db.scalars(
            select(Order)
            .where(Order.user_id == user.id)
            .order_by(Order.id.desc())  # newest first: that is the one being looked for
            .options(
                selectinload(Order.items).joinedload(OrderItem.product),
                joinedload(Order.shipping_address),
            )
        )
    )


def get_order(db: Session, order_id: int, user: User) -> Order | None:
    # Whose it is belongs in the WHERE, not in an `if` afterwards. A query that can only
    # return this person's orders cannot be made to return somebody else's by mistake.
    return db.scalars(
        select(Order)
        .where(Order.id == order_id, Order.user_id == user.id)
        .options(
            selectinload(Order.items).joinedload(OrderItem.product),
            joinedload(Order.shipping_address),
        )
    ).first()


# How long a sign-in lasts. Short enough that a token copied from a shared computer stops
# working by itself; long enough not to interrupt someone in the middle of buying.
SESSION_LIFETIME = timedelta(hours=24)


def register_user(db: Session, email: str, password: str, full_name: str) -> User | None:
    # The password is turned into a hash here and the plain one is never kept, not in a
    # variable that outlives this call, not in a column, and never written to a log.
    user = User(email=email, password_hash=hash_password(password), full_name=full_name)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Asked for, not checked first. A "is this email free?" query followed by an
        # INSERT has a gap in between, and two people registering at the same instant
        # both pass it. The unique constraint is the only answer that cannot be raced.
        db.rollback()
        return None  # the email is taken; the route turns this into a 409
    return user


def login(db: Session, email: str, password: str) -> UserSession | None:
    user = db.scalars(select(User).where(User.email == email)).first()

    # The hashing work is done even when there is no such user, against a throwaway hash.
    # Otherwise "this email is not registered" comes back noticeably faster than "wrong
    # password", and that difference alone tells a stranger who shops here.
    password_matches = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if user is None or not password_matches:
        # The customer is told nothing about why (see the route), but the log is for us
        # and the reason is exactly what we need. This is the only place that knows it,
        # which is why this log lives in the service and not in the route like the others.
        #
        #   · unknown_email over and over, each time a different address: somebody is
        #     trying a list of emails and passwords stolen from another site.
        #   · wrong_password over and over on the same user.id: somebody is guessing the
        #     password of one particular account.
        #
        # The password is never logged, not even the wrong one: it is often the right
        # password for another site, or the right one with a typo.
        # The email is not logged either. For a known user, user.id says who it is; for an
        # unknown one, its fingerprint is enough to see the same address coming back.
        log.warning(
            "sign-in failed",
            extra={
                "event.action": "user.login",
                "event.outcome": "failure",
                "event.reason": "unknown_email" if user is None else "wrong_password",
                **({"user.id": user.id} if user else {"shop.email_ref": fingerprint(email.lower())}),
            },
        )
        return None  # one None for both reasons: the route must not say which it was

    session = UserSession(
        token=secrets.token_urlsafe(32),  # same idea as the cart token: long and random
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + SESSION_LIFETIME,
    )
    db.add(session)
    db.commit()
    # user.id is an ECS field: when a name already exists in ECS, it is used instead of
    # inventing one under shop. The session token, like the cart token, is only fingerprinted.
    log.info(
        f"user {user.id} signed in",
        extra={
            "event.action": "user.login",
            "event.outcome": "success",
            "user.id": user.id,
            "shop.session_ref": fingerprint(session.token),
        },
    )
    return session


def get_user_by_session(db: Session, token: str) -> User | None:
    session = db.scalars(
        select(UserSession)
        .where(UserSession.token == token)
        .options(joinedload(UserSession.user))
    ).first()
    # Expiry is checked here and not only when the row is created: the row sitting in the
    # table is not what makes a session valid, the date is.
    if session is None or session.expires_at <= datetime.now(timezone.utc):
        return None
    return session.user


def logout(db: Session, token: str) -> None:
    # The row is deleted, so the token stops working everywhere at once. Forgetting it in
    # the browser alone would leave it usable by anyone who had already copied it.
    db.execute(delete(UserSession).where(UserSession.token == token))
    db.commit()


def get_active_address(db: Session, user: User, is_billing: bool) -> Address | None:
    return db.scalars(
        select(Address).where(
            Address.user_id == user.id,
            Address.is_billing == is_billing,
            Address.is_active.is_(True),
        )
    ).first()


def list_addresses(db: Session, user: User) -> list[Address]:
    # Only the ones in use. The retired rows are still in the table, kept for the orders
    # that point at them, but they are nobody's business on screen.
    return list(
        db.scalars(
            select(Address)
            .where(Address.user_id == user.id, Address.is_active.is_(True))
            .order_by(Address.is_billing)  # shipping first, always the same order
        )
    )


def save_address(db: Session, user: User, is_billing: bool, data: AddressIn) -> Address:
    """Set this person's shipping or billing address by adding a NEW row.

    Nothing here is ever an UPDATE of an address. Changing one retires the row in use and
    writes another, so an order that points at the old one keeps the address it was
    actually sent to, however many times the person moves house afterwards. Exactly the
    lesson of the frozen price in order_items, arrived at from the other direction.
    """
    # Retire and insert in ONE transaction. In between there is no active address of this
    # kind, and the partial unique index is what guarantees there is never more than one.
    db.execute(
        update(Address)
        .where(
            Address.user_id == user.id,
            Address.is_billing == is_billing,
            Address.is_active.is_(True),
        )
        .values(is_active=False)
    )
    address = Address(
        user_id=user.id,
        is_billing=is_billing,
        is_active=True,
        recipient_name=data.recipient_name,
        street=data.street,
        city=data.city,
        postal_code=data.postal_code,
        country=data.country.upper(),
    )
    db.add(address)
    db.commit()
    return address


def deactivate_address(db: Session, user: User, is_billing: bool) -> bool:
    """Stop using this address, without removing the row.

    Deleting it would not be possible anyway: an order may point at it, and the foreign
    key exists precisely to stop that order losing the address it was sent to.
    """
    result = db.execute(
        update(Address)
        .where(
            Address.user_id == user.id,
            Address.is_billing == is_billing,
            Address.is_active.is_(True),
        )
        .values(is_active=False)
    )
    db.commit()
    return result.rowcount > 0  # False when there was no address in use to retire
