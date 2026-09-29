from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Identity, String, Text, func
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
    __table_args__ = (CheckConstraint("total_cents >= 0", name="ck_orders_total_cents"),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    customer_email: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), server_default="paid")
    total_cents: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


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
