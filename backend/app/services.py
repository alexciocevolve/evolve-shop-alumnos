from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product


def get_product(db: Session, product_id: int) -> Product | None:
    return db.get(Product, product_id)  # None when there is no such row


def list_products(
    db: Session, category: str | None, cursor: int, limit: int
) -> tuple[list[Product], int | None]:
    # Keyset pagination: "give me the rows AFTER the last one I saw" (id > cursor).
    # Unlike OFFSET, the database jumps straight to that point through the primary-key
    # index, and rows inserted meanwhile can never shift a page or repeat an item.
    query = select(Product).where(Product.id > cursor)
    if category is not None:
        query = query.where(Product.category == category)

    # Ask for one row more than the page size: if it arrives, there is a next page,
    # and we know it without running a second query.
    rows = list(db.scalars(query.order_by(Product.id).limit(limit + 1)))
    if len(rows) > limit:
        page = rows[:limit]
        return page, page[-1].id
    return rows, None
