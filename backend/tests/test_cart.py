"""The cart: a PUT that sets rather than adds, and prices that are always today's."""

import pytest

from app import services
from app.models import Product

LAPTOP = 1
MOUSE = 3


def test_a_new_cart_is_empty_and_has_a_token_nobody_can_guess(db):
    cart = services.create_cart(db)
    assert cart.items == []
    # 32 random bytes in url-safe base64. A sequential id would mean that changing the
    # number in the browser showed somebody else's cart.
    assert len(cart.token) >= 40


def test_setting_a_line_puts_the_product_in_the_cart(db, cart):
    updated = services.set_cart_item(db, cart, LAPTOP, 2)
    assert [(i.product_id, i.quantity) for i in updated.items] == [(LAPTOP, 2)]


def test_setting_the_same_line_twice_does_not_add_it_twice(db, cart):
    services.set_cart_item(db, cart, LAPTOP, 2)
    updated = services.set_cart_item(db, cart, LAPTOP, 2)
    # PUT says "leave it at this quantity", so a retry after a dropped connection is
    # harmless. This is the whole reason the verb is PUT and not POST.
    assert [(i.product_id, i.quantity) for i in updated.items] == [(LAPTOP, 2)]


def test_setting_a_different_quantity_replaces_it(db, cart):
    services.set_cart_item(db, cart, LAPTOP, 2)
    updated = services.set_cart_item(db, cart, LAPTOP, 5)
    assert [(i.product_id, i.quantity) for i in updated.items] == [(LAPTOP, 5)]


def test_a_product_that_does_not_exist_is_none(db, cart):
    assert services.set_cart_item(db, cart, 999, 1) is None


def test_asking_for_more_than_there_is_says_how_many_are_left(db, cart):
    product = db.get(Product, LAPTOP)
    product.stock = 3
    db.commit()

    with pytest.raises(ValueError) as error:
        services.set_cart_item(db, cart, LAPTOP, 4)

    # The message is the one the shopper reads, so it has to name the product and both
    # numbers - not "insufficient stock", which tells nobody what to do next.
    assert str(error.value) == f"Insufficient stock for {product.name}: 3 left, 4 requested"


def test_asking_for_exactly_what_is_left_is_allowed(db, cart):
    product = db.get(Product, LAPTOP)
    product.stock = 3
    db.commit()

    updated = services.set_cart_item(db, cart, LAPTOP, 3)  # 3 of 3, not "almost too many"
    assert updated.items[0].quantity == 3


def test_removing_a_line_says_whether_there_was_one(db, cart):
    services.set_cart_item(db, cart, LAPTOP, 1)
    assert services.remove_cart_item(db, cart, LAPTOP) is True
    # Removing it again is a different situation, and the route turns it into a 404.
    assert services.remove_cart_item(db, cart, LAPTOP) is False


def test_the_total_is_the_sum_of_the_lines(db, cart):
    services.set_cart_item(db, cart, LAPTOP, 2)
    cart = services.set_cart_item(db, cart, MOUSE, 1)

    laptop, mouse = db.get(Product, LAPTOP), db.get(Product, MOUSE)
    assert services.cart_total_cents(cart) == laptop.price_cents * 2 + mouse.price_cents


def test_the_cart_shows_todays_price_and_not_the_price_when_it_was_added(db, cart):
    services.set_cart_item(db, cart, LAPTOP, 1)
    db.get(Product, LAPTOP).price_cents = 1
    db.commit()

    # This is the half of the lesson that cart_items has no price column for. Compare with
    # test_orders.py, where the opposite has to be true.
    assert services.cart_total_cents(services.get_cart(db, cart.token)) == 1


def test_a_cart_token_that_does_not_exist_is_none(db):
    assert services.get_cart(db, "not-a-real-token") is None


def test_reading_a_cart_does_not_cost_one_query_per_line(db, cart, count_queries):
    services.set_cart_item(db, cart, LAPTOP, 1)
    services.set_cart_item(db, cart, MOUSE, 1)
    count_queries.clear()

    loaded = services.get_cart(db, cart.token)
    total = services.cart_total_cents(loaded)  # touches every line's product

    assert total > 0
    # One for the cart, one for its lines, one for the products they point at.
    assert len(count_queries) <= 3, f"N+1: {len(count_queries)} queries for a two-line cart"
