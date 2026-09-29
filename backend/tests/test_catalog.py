"""The catalog: keyset pagination, the category filter after the schema moved, and the
N+1 that nothing on screen would have shown."""

from app import services
from app.models import Product

TOTAL_PRODUCTS = 36


def test_a_page_returns_at_most_the_limit_and_says_where_to_continue(db):
    page, next_cursor = services.list_products(db, category=None, cursor=0, limit=5)
    assert [p.id for p in page] == [1, 2, 3, 4, 5]
    # The cursor is the last id returned, not a page number: that is what makes it survive
    # rows being inserted while somebody is scrolling.
    assert next_cursor == 5


def test_following_the_cursor_neither_repeats_nor_skips_a_row(db):
    seen: list[int] = []
    cursor: int | None = 0
    pages = 0
    while cursor is not None:
        page, cursor = services.list_products(db, category=None, cursor=cursor, limit=5)
        seen.extend(p.id for p in page)
        pages += 1
        assert pages < 20  # a cursor that never ends would otherwise hang the suite

    assert seen == sorted(seen)
    assert len(seen) == len(set(seen)) == TOTAL_PRODUCTS


def test_the_last_page_says_there_is_no_next_one(db):
    page, next_cursor = services.list_products(db, category=None, cursor=35, limit=5)
    assert [p.id for p in page] == [36]
    assert next_cursor is None


def test_a_last_page_that_is_exactly_full_still_says_there_is_no_next_one(db):
    # The case the limit+1 trick exists for. Asking for 12 when exactly 12 remain must not
    # promise a thirteenth: a phantom page shows an empty screen at the end of the list.
    page, next_cursor = services.list_products(db, category=None, cursor=24, limit=12)
    assert len(page) == 12
    assert next_cursor is None


def test_filtering_by_category_returns_only_that_category(db):
    page, _ = services.list_products(db, category="laptops", cursor=0, limit=100)
    assert len(page) > 0
    assert {p.category.name for p in page} == {"laptops"}


def test_the_category_filter_still_paginates(db):
    first, cursor = services.list_products(db, category="laptops", cursor=0, limit=5)
    assert cursor is not None
    second, _ = services.list_products(db, category="laptops", cursor=cursor, limit=5)
    assert {p.id for p in first}.isdisjoint({p.id for p in second})


def test_an_unknown_category_is_an_empty_page_and_not_an_error(db):
    page, next_cursor = services.list_products(db, category="toys", cursor=0, limit=12)
    assert page == []
    assert next_cursor is None


def test_products_with_no_stock_are_still_listed(db):
    page, _ = services.list_products(db, category=None, cursor=0, limit=100)
    assert any(p.stock == 0 for p in page)  # out of stock is a label, not a reason to hide


def test_a_product_that_does_not_exist_is_none_and_not_an_exception(db):
    assert services.get_product(db, 999) is None
    assert services.get_product(db, 1) is not None


def test_a_whole_page_with_its_category_names_is_a_single_query(db, count_queries):
    page, _ = services.list_products(db, category=None, cursor=0, limit=12)
    names = [p.category.name for p in page]  # what the route does for every product

    assert len(names) == 12
    # Without joinedload this is 13: one for the page and one per product. It is invisible
    # on screen, invisible in the answer, and only shows up by counting.
    assert len(count_queries) == 1, f"N+1: {len(count_queries)} queries for one page"


def test_the_categories_come_back_in_a_stable_order(db):
    # The filter buttons must not swap places between two loads of the same page.
    names = [c.name for c in services.list_categories(db)]
    assert names == sorted(names)
    assert names == ["laptops", "monitors", "networking", "peripherals", "storage"]


def test_every_product_points_at_a_category_row(db):
    # What the foreign key buys: after the text column was dropped, nothing can be orphaned.
    assert db.query(Product).filter(Product.category_id.is_(None)).count() == 0
