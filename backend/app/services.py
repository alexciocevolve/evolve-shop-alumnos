import secrets
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.orm import Session, joinedload, selectinload

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
from app.payments import PaymentDeclined
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


def create_order(db: Session, cart: Cart, user: User, pay: Callable) -> Order:
    # The whole checkout is ONE transaction: everything below happens, or nothing does.
    #
    # And from this phase on, one of the things that happens inside it is A CALL OVER THE
    # INTERNET. That is new, and it is the uncomfortable part of the design, so it is
    # written down rather than hidden:
    #
    #   · The products above are locked with SELECT ... FOR UPDATE. While Stripe thinks,
    #     nobody else can buy them. Stripe answering slowly becomes the shop being slow -
    #     the concurrency test of cp4 explains why that matters.
    #   · If the process dies between the charge and the commit, Stripe has the money and
    #     this shop has no order. Nobody finds out until the customer complains.
    #
    # Moving the call outside the transaction does not fix it, it only swaps which half
    # can be orphaned. A database transaction and a call to somebody else's server cannot
    # be made atomic, and every phase after this one is a way of living with that.
    #
    # `pay` arrives as an argument instead of being imported so the tests can hand over a
    # function that refuses, times out, or counts how many times it was called.
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
    # flush and not commit: this asks the database for the id without ending the
    # transaction. The id is needed before charging, because the charge has to say which
    # order it is paying for - and if the charge is refused, none of this ever existed.
    db.flush()

    # Read now, while the order is still in the session: after a rollback these attributes
    # are gone, and the log lines below need them most exactly then.
    order_id, amount_cents = order.id, order.total_cents
    # The payment lines say who and what, never how: no email, no card, no key. The card
    # is not even ours to log (Stripe holds it), which is the point of using Stripe.
    who = {"user.id": user.id, "shop.order_id": order_id, "shop.amount_cents": amount_cents}

    started = time.perf_counter()
    try:
        charge = _charge_for(pay, order, user, cart, products)
    except Exception as e:
        # How long Stripe took is how long these products stayed locked for everybody else,
        # so it goes in every payment line, the failed ones included.
        took_ms = round((time.perf_counter() - started) * 1000, 1)
        if isinstance(e, PaymentDeclined):
            # An ordinary no. The customer is told, nothing was charged, nothing to fix.
            log.warning(
                "payment declined",
                extra={
                    "event.action": "payment.charge",
                    "event.outcome": "failure",
                    "event.reason": "declined",
                    "event.duration_ms": took_ms,
                    "error.message": str(e),
                    **who,
                },
            )
        else:
            # NOT a decline, and an error rather than a warning, because the outcome is
            # UNKNOWN: Stripe may have charged the card and the answer got lost on the way
            # back. Before anybody tells the customer "you were not charged", somebody has
            # to look for shop.order_id in the Stripe dashboard.
            log.error(
                "payment failed, outcome unknown",
                extra={
                    "event.action": "payment.charge",
                    "event.outcome": "unknown",
                    "event.reason": "gateway_error",
                    "event.duration_ms": took_ms,
                    "error.type": type(e).__name__,
                    "error.message": str(e),
                    **who,
                },
            )
        # The card was refused, or the gateway broke, or the network did. Either way the
        # order has already been built and the stock already taken, so it all has to go.
        #
        # This rollback is written down rather than left to chance. get_db closes the
        # session when the request ends and that WOULD undo the flush - but "somebody
        # downstream will clean this up" is a bad thing to rely on for the one path where
        # the shop has just taken stock off the shelf and failed to get paid for it. It
        # also means the service behaves the same when it is called outside a request.
        db.rollback()
        raise
    took_ms = round((time.perf_counter() - started) * 1000, 1)
    order.payment_intent_id = charge.payment_intent_id

    log.info(
        f"payment for order {order_id} charged",
        extra={
            "event.action": "payment.charge",
            "event.outcome": "success",
            "event.duration_ms": took_ms,
            # Stripe's name for the payment: what joins this line to their dashboard.
            "shop.payment_intent_id": charge.payment_intent_id,
            # The amount STRIPE says it charged, next to the one we asked for. Equal today;
            # a dashboard that compares the two is how anybody would notice if they stopped
            # being equal.
            "shop.charged_cents": charge.amount_cents,
            **who,
        },
    )

    db.delete(cart)  # the lines go with it, and the cart has served its purpose
    try:
        db.commit()
    except Exception:
        # The worst line this shop can write: Stripe HAS the money and there is no order.
        # The comment at the top of this function says it can happen, and this is what is
        # left when it does. The log is then the only record that somebody paid, so it
        # carries exactly what is needed to find the payment and refund it.
        log.critical(
            "charged, but the order was not saved",
            extra={
                "event.action": "payment.orphaned",
                "event.outcome": "failure",
                "shop.payment_intent_id": charge.payment_intent_id,
                "shop.charged_cents": charge.amount_cents,
                **who,
            },
        )
        raise
    return order


def _charge_for(pay: Callable, order: Order, user: User, cart: Cart, products: dict):
    """Build what the gateway is told about this order, and ask it to charge."""
    lines = [f"{item.quantity} x {products[item.product_id].name}" for item in cart.items]
    return pay(
        amount_cents=order.total_cents,
        # What the buyer reads on the receipt Stripe sends them.
        description=f"Order #{order.id}: " + ", ".join(lines),
        # What we read in the Stripe dashboard. Never shown to the buyer. Values are
        # capped at 500 characters by Stripe, so a very long order is cut rather than
        # rejected - the lines live in order_items anyway, this is only for looking things
        # up by eye. order_id is the one that matters: it is what turns a payment in their
        # dashboard back into an order in ours.
        metadata={
            "order_id": str(order.id),
            "user_id": str(user.id),
            "items": "; ".join(lines)[:500],
        },
        receipt_email=order.customer_email,
    )


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
