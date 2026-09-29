"""Checkout: the price frozen at the moment of buying, all-or-nothing, and orders that
belong to exactly one person."""

import pytest

from app import services
from app.models import Cart, CartItem, Order, Product

LAPTOP = 1
MOUSE = 3


def test_an_empty_cart_cannot_be_ordered(db, cart, user, shipping_address):
    with pytest.raises(ValueError, match="The cart is empty"):
        services.create_order(db, cart, user)


def test_an_order_needs_somewhere_to_go(db, cart, user):
    # `user` has no address in this test: the fixture that adds one is not requested.
    services.set_cart_item(db, cart, LAPTOP, 1)
    with pytest.raises(ValueError, match="shipping address is required"):
        services.create_order(db, cart, user)


def test_an_order_records_who_bought_it_and_where_it_went(db, cart, user, shipping_address):
    services.set_cart_item(db, cart, LAPTOP, 2)

    order = services.create_order(db, cart, user)

    assert order.user_id == user.id
    assert order.customer_email == user.email
    assert order.shipping_address_id == shipping_address.id
    assert order.status == "paid"


def test_the_total_is_worked_out_on_the_server(db, cart, user, shipping_address):
    services.set_cart_item(db, cart, LAPTOP, 2)
    services.set_cart_item(db, cart, MOUSE, 3)
    laptop, mouse = db.get(Product, LAPTOP), db.get(Product, MOUSE)
    expected = laptop.price_cents * 2 + mouse.price_cents * 3

    order = services.create_order(db, cart, user)

    # Nothing about money arrives from the client: not a price, not a line total, not this.
    assert order.total_cents == expected
    assert order.total_cents == sum(i.price_cents * i.quantity for i in order.items)


def test_buying_takes_the_units_out_of_stock(db, cart, user, shipping_address):
    before = db.get(Product, LAPTOP).stock
    services.set_cart_item(db, cart, LAPTOP, 2)

    services.create_order(db, cart, user)

    assert db.get(Product, LAPTOP).stock == before - 2


def test_the_cart_disappears_once_it_has_become_an_order(db, cart, user, shipping_address):
    token = cart.token
    services.set_cart_item(db, cart, LAPTOP, 1)

    services.create_order(db, cart, user)

    assert services.get_cart(db, token) is None
    # And its lines went with it, through the cascade rather than by hand.
    assert db.query(CartItem).filter(CartItem.cart_token == token).count() == 0


def test_changing_the_price_afterwards_does_not_rewrite_the_order(db, cart, user, shipping_address):
    # THE lesson of the cart checkpoint, and the reason order_items has a price column
    # while cart_items does not.
    catalogue_price = db.get(Product, LAPTOP).price_cents
    services.set_cart_item(db, cart, LAPTOP, 2)
    order = services.create_order(db, cart, user)
    paid, total = order.items[0].price_cents, order.total_cents
    # Read from the catalog, not from the order: otherwise this test would still pass if
    # the wrong price had been frozen, as long as it went on being wrong.
    assert paid == catalogue_price

    db.get(Product, LAPTOP).price_cents = 1
    db.commit()
    db.expire_all()  # force a real read, so this cannot pass on a stale object in memory

    reread = services.get_order(db, order.id, user)
    assert reread.items[0].price_cents == paid
    assert reread.total_cents == total
    assert db.get(Product, LAPTOP).price_cents == 1  # the catalog really did change


def test_one_line_short_of_stock_cancels_the_whole_order(db, cart, user, shipping_address):
    services.set_cart_item(db, cart, LAPTOP, 1)
    services.set_cart_item(db, cart, MOUSE, 1)
    laptop_stock = db.get(Product, LAPTOP).stock

    # Somebody else buys all the mice between putting them in the cart and paying, which
    # is exactly why the check at checkout is the one that counts.
    db.get(Product, MOUSE).stock = 0
    db.commit()

    with pytest.raises(ValueError, match="Insufficient stock"):
        services.create_order(db, cart, user)

    db.expire_all()
    assert db.get(Product, LAPTOP).stock == laptop_stock  # the servable line did not move
    assert db.query(Order).count() == 0  # and no half-made order was left behind
    assert db.get(Cart, cart.token) is not None  # the cart survives, so it can be fixed


def test_an_order_can_only_be_read_by_the_person_who_placed_it(
    db, cart, user, other_user, shipping_address
):
    services.set_cart_item(db, cart, LAPTOP, 1)
    order = services.create_order(db, cart, user)

    assert services.get_order(db, order.id, user) is not None
    # None, not an exception: the route turns it into the same 404 as an order that does
    # not exist, so asking cannot be used to find out which order numbers are real.
    assert services.get_order(db, order.id, other_user) is None


def test_an_order_that_does_not_exist_is_none(db, user):
    assert services.get_order(db, 999, user) is None


def test_the_list_of_orders_holds_only_your_own_and_the_newest_first(
    db, user, other_user, shipping_address
):
    ids = []
    for _ in range(2):
        cart = services.create_cart(db)
        services.set_cart_item(db, cart, LAPTOP, 1)
        ids.append(services.create_order(db, cart, user).id)

    assert services.list_orders(db, other_user) == []
    assert [o.id for o in services.list_orders(db, user)] == sorted(ids, reverse=True)
