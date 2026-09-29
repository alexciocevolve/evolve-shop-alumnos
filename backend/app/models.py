from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    # unique: the name identifies the category, so the database refuses two "laptops".
    name: Mapped[str] = mapped_column(String(50), unique=True)
    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"
    # Named constraints and server defaults live in the model on purpose: that way
    # autogenerate carries them into the migration and the rule lives in the database,
    # not only in the Python code.
    __table_args__ = (
        CheckConstraint("price_cents >= 0", name="ck_products_price_cents"),
        CheckConstraint("stock >= 0", name="ck_products_stock"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, server_default="")
    # After CONTRACT there is only one way to name the category: a reference to the row in
    # categories. The name itself is stored once, in that table, instead of repeated in
    # every product, so renaming a category is one UPDATE and a typo cannot invent one.
    # The foreign key is named on purpose: PostgreSQL would invent a name, and then the
    # downgrade would not know what to drop (Alembic warns about exactly this).
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", name="fk_products_category_id"), index=True
    )
    price_cents: Mapped[int]  # cents, never float
    stock: Mapped[int] = mapped_column(server_default="0")
    image_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Reading product.category now gives the Category row, not a string: product.category.name.
    category: Mapped["Category"] = relationship(back_populates="products")


class Cart(Base):
    __tablename__ = "carts"
    # The identifier IS the token: random and long. With a sequential number,
    # changing it in the browser would show someone else's cart.
    token: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    items: Mapped[list["CartItem"]] = relationship(
        back_populates="cart", cascade="all, delete-orphan"
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_cart_items_quantity"),)

    # Composite primary key: one row per product per cart, no duplicates possible.
    cart_token: Mapped[str] = mapped_column(
        ForeignKey("carts.token", ondelete="CASCADE", name="fk_cart_items_cart_token"),
        primary_key=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", name="fk_cart_items_product_id"), primary_key=True
    )
    quantity: Mapped[int]
    # Note what is NOT here: a price. The cart shows TODAY's price, read from products.
    cart: Mapped["Cart"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("total_cents >= 0", name="ck_orders_total_cents"),
        # From now on an order belongs to somebody. The column is nullable and the rule is
        # a CHECK instead, because orders placed before this rule existed have no owner and
        # history cannot be rewritten: the migration adds this one NOT VALID, so it applies
        # to every new order without failing on the old ones.
        CheckConstraint("user_id IS NOT NULL", name="ck_orders_user_id_required"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    # Who bought it. Nullable in the column only for the orders that came before.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", name="fk_orders_user_id"), index=True
    )
    # Kept even though the user is now known: it is the address the order was sent to,
    # frozen the same way the price is. Changing the account email later must not rewrite
    # where this order was confirmed.
    customer_email: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), server_default="paid")
    total_cents: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Which address this went to. Nullable, because an order placed without signing in
    # has none, and because that is what lets this column be added without breaking a
    # single order that already exists.
    shipping_address_id: Mapped[int | None] = mapped_column(
        ForeignKey("addresses.id", name="fk_orders_shipping_address_id")
    )
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    # Pointing at the row is enough to keep the address as it was, because an address row
    # is never changed: editing one writes a NEW row and retires the old one. Same lesson
    # as the price in order_items, reached a different way.
    shipping_address: Mapped["Address | None"] = relationship()
    user: Mapped["User | None"] = relationship()


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_order_items_quantity"),)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE", name="fk_order_items_order_id"),
        primary_key=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", name="fk_order_items_product_id"), primary_key=True
    )
    quantity: Mapped[int]
    # And here there IS a price: the price at purchase time. If the product
    # goes up tomorrow, today's order must not change.
    price_cents: Mapped[int]
    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    # unique: the email IS the login name, so the database itself refuses a second one.
    email: Mapped[str] = mapped_column(String(200), unique=True)
    # Never the password: only a value derived from it, which cannot be turned back.
    password_hash: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    addresses: Mapped[list["Address"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base):
    # Named UserSession and not Session because sqlalchemy.orm.Session already exists,
    # and two things called Session in the same file is a bug waiting to happen.
    __tablename__ = "sessions"

    # Same idea as carts: a long random token identifies the session, and it is the key.
    token: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", name="fk_sessions_user_id"), index=True
    )
    # A session that lasts forever is a password that never expires.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user: Mapped["User"] = relationship()


class Address(Base):
    __tablename__ = "addresses"
    __table_args__ = (
        # Rows are never edited, so a person accumulates old addresses; what has to stay
        # unique is the CURRENT one. A partial unique index says exactly that: at most one
        # active shipping address and one active billing address each, and any number of
        # retired ones. The rule is in the database, so no amount of clicking can break it.
        Index(
            "uq_addresses_one_active",
            "user_id",
            "is_billing",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", name="fk_addresses_user_id"), index=True
    )
    # What kind of address this is, kept as a column here rather than as a row in a
    # separate "address types" table. A second table would earn its keep if the types
    # carried data of their own or were added without a deployment; two fixed kinds that
    # the code has to know about anyway do not, and the join would be for nothing.
    is_billing: Mapped[bool] = mapped_column(server_default=text("false"))
    # Whether this is the address the person uses now. Changing an address retires the old
    # row and adds a new one, so the old one is still there for the orders that point at
    # it. This flag is the user's business only: an order ignores it completely, because
    # an order points at one exact row and does not care whether it is still in use.
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    recipient_name: Mapped[str] = mapped_column(String(200))
    street: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    postal_code: Mapped[str] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(2), server_default="ES")  # ISO 3166-1
    user: Mapped["User"] = relationship(back_populates="addresses")


class ProductPriceHistory(Base):
    __tablename__ = "product_price_history"
    __table_args__ = (
        # Every question this table exists to answer is about ONE product over TIME, so the
        # index covers both columns in that order: find the product, then read its rows
        # already sorted. An index on product_id alone would still have to sort afterwards.
        Index("ix_product_price_history_product", "product_id", "changed_at"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    # ON DELETE CASCADE, which is a real decision and not a default: the history of a
    # product that no longer exists cannot be read by anybody, because every route reaches
    # it through the product. Keeping those rows would be keeping rubbish nobody can see.
    product_id: Mapped[int] = mapped_column(
        ForeignKey(
            "products.id", ondelete="CASCADE", name="fk_product_price_history_product_id"
        )
    )
    # A row is a TRANSITION, not a state: it holds the price before and the price after.
    # Storing only the new price would need an invented first row for the price a product
    # was born with, and then "the history is empty" and "it never changed" would look the
    # same. Two columns make each row answer on its own: it went from this to that.
    previous_price_cents: Mapped[int]
    price_cents: Mapped[int]
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped["Product"] = relationship()

    # NOTE: nothing writes to this table yet. The table comes first on its own so that the
    # question of WHO fills it stays open and gets answered separately - which is the whole
    # point of the checkpoint.
