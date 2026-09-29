"""The price history, which no Python code writes.

Everything here is really a test of a database trigger, so the tests change prices the way
anything else in the world would - with an UPDATE - and then ask the service what it can
see. That is the point of the checkpoint: the guarantee does not live in the application,
so a test that only went through the application would be testing the wrong thing.
"""

from sqlalchemy import text

from app import services
from app.models import Product


def change_price(db, product_id: int, price_cents: int) -> None:
    """Change a price in plain SQL, as far away from the application as a test can get.

    Deliberately not services.create_order or any ORM object: this is a stand-in for the
    import script, the other service and the colleague with psql open. If the history only
    worked when the change came through our code, this function would record nothing.
    """
    db.execute(
        text("UPDATE products SET price_cents = :price WHERE id = :id"),
        {"price": price_cents, "id": product_id},
    )


def test_a_product_that_does_not_exist_is_not_a_product_without_changes(db):
    # The whole reason the service returns None rather than an empty list. These two
    # situations must never arrive at the caller looking the same.
    assert services.list_price_history(db, 999_999) is None


def test_a_product_that_has_never_changed_price_has_an_empty_history(db):
    history = services.list_price_history(db, 1)

    assert history == []
    # An empty collection, not a missing resource: this is a real and complete answer.
    assert history is not None


def test_changing_a_price_without_touching_the_application_records_it(db):
    before = db.get(Product, 1).price_cents

    change_price(db, 1, 12345)

    entry = services.list_price_history(db, 1)[0]
    assert entry.previous_price_cents == before
    assert entry.price_cents == 12345
    # Nothing in app/ wrote that row. If the trigger were dropped, this is the test that
    # would notice - and the only kind of test that could.


def test_saving_the_same_price_again_is_not_a_change(db):
    price = db.get(Product, 1).price_cents

    change_price(db, 1, price)

    assert services.list_price_history(db, 1) == []


def test_restocking_a_product_is_not_a_price_change(db):
    db.execute(text("UPDATE products SET stock = 99 WHERE id = 1"))

    # Without `OF price_cents` on the trigger, this would have written a row into the
    # history of PRICES because the row was updated at all.
    assert services.list_price_history(db, 1) == []


def test_the_history_reads_forwards(db):
    change_price(db, 1, 11100)
    change_price(db, 1, 22200)
    change_price(db, 1, 33300)

    history = services.list_price_history(db, 1)

    assert [entry.price_cents for entry in history] == [11100, 22200, 33300]
    # Each row is a transition and stands on its own: it says where the price came from
    # without needing the row before it.
    assert [entry.previous_price_cents for entry in history[1:]] == [11100, 22200]
    # And these three share a changed_at to the microsecond, because now() in PostgreSQL
    # is the start of the transaction. Their order comes from the id tie-breaker in the
    # service; ordering by the date alone would leave it to the database to decide.
    assert len({entry.changed_at for entry in history}) == 1


def test_two_changes_with_the_same_timestamp_still_have_one_right_order(db):
    # The test above cannot fail: removing the id tie-breaker from the service leaves it
    # green, because PostgreSQL happens to hand rows back in the order they were written.
    # "Happens to" is not a guarantee, so the ambiguous case is built here on purpose -
    # two rows with the SAME changed_at, inserted with the LATER id first.
    #
    # Without the tie-breaker the database is free to return either order, and in practice
    # returns the one it stored. With it, the answer is the same every time on every
    # machine. Nothing above would have noticed the difference.
    db.execute(
        text(
            "INSERT INTO product_price_history"
            " (id, product_id, previous_price_cents, price_cents, changed_at)"
            " VALUES (900, 1, 200, 300, now()), (800, 1, 100, 200, now())"
        )
    )

    history = services.list_price_history(db, 1)

    assert [entry.id for entry in history] == [800, 900]


def test_one_product_does_not_see_another_product_changes(db):
    change_price(db, 1, 55500)

    assert services.list_price_history(db, 2) == []
