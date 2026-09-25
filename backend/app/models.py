from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Identity, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


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
    category: Mapped[str] = mapped_column(String(50), index=True)  # every listing filters by it
    price_cents: Mapped[int]  # cents, never float
    stock: Mapped[int] = mapped_column(server_default="0")
    image_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
