"""Tests of the test setup itself. If these fail, no other failure means anything."""

from sqlalchemy import text

from app import services
from app.models import Product


def test_the_test_database_is_not_the_development_one(db):
    name = db.execute(text("SELECT current_database()")).scalar()
    assert name == "shop_test"


def test_the_migrations_left_their_seed_data(db):
    assert db.query(Product).count() == 36


def test_what_a_test_writes_does_not_survive_it(db):
    services.create_cart(db)
    assert db.execute(text("SELECT count(*) FROM carts")).scalar() == 1
    # The next test asserts the other half of this: that the cart above is gone.


def test_and_the_next_test_starts_clean(db):
    assert db.execute(text("SELECT count(*) FROM carts")).scalar() == 0
