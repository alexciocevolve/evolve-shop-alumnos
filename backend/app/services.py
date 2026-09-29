from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Category, Product


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
