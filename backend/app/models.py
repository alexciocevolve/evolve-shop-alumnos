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
