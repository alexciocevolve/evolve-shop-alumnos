import secrets

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.orm import Session, joinedload, selectinload

from app.config import PLACEHOLDER_CUSTOMER_EMAIL
from app.models import Cart, CartItem, Category, Order, OrderItem, Product


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


def create_order(db: Session, cart: Cart) -> Order:
    # The whole checkout is ONE transaction: everything below happens, or nothing does.
    if not cart.items:
        raise ValueError("The cart is empty")

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
        customer_email=PLACEHOLDER_CUSTOMER_EMAIL,
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


def get_order(db: Session, order_id: int) -> Order | None:
    return db.scalars(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items).joinedload(OrderItem.product))
    ).first()
