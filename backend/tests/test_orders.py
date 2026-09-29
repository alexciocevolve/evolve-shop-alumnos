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
    # Third meaning of this word in three objectives. See the block at the end.
    assert order.status == "pending_payment"


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


# --- Paying for it -----------------------------------------------------------------
# From objective 17 the order is created FIRST and paid for somewhere else. These tests
# never reach Stripe: the `gateway` fixture stands in for it, which is the only way to
# decide what a session comes back as.


def test_an_order_is_born_owing_money(db, cart, user, shipping_address):
    services.set_cart_item(db, cart, LAPTOP, 1)

    order = services.create_order(db, cart, user)

    # The word phase 0 caught lying, on its third meaning. Nobody has paid, and for the
    # first time in this project the shop says so.
    assert order.status == "pending_payment"
    assert order.payment_intent_id is None


def test_the_lines_sent_to_stripe_are_the_lines_of_the_order(
    db, cart, user, shipping_address, gateway
):
    services.set_cart_item(db, cart, LAPTOP, 2)
    order = services.create_order(db, cart, user)

    url = services.start_checkout(db, order, gateway)

    assert len(gateway.starts) == 1, "the gateway must be asked exactly once per order"
    asked = gateway.starts[0]
    assert asked["order_id"] == order.id
    assert asked["customer_email"] == user.email
    assert url.startswith("https://")

    # Real line items, which the previous design could not send: a PaymentIntent takes one
    # number. This is what puts the product name on Stripe's page and on the receipt.
    laptop = db.get(Product, LAPTOP)
    line = asked["lines"][0]
    assert line["quantity"] == 2
    assert line["price_data"]["product_data"]["name"] == laptop.name
    assert line["price_data"]["unit_amount"] == laptop.price_cents
    # And Stripe adds the lines up itself now, so its sum has to be our total.
    total = sum(l["price_data"]["unit_amount"] * l["quantity"] for l in asked["lines"])
    assert total == order.total_cents


def test_stripe_is_told_the_frozen_price_and_not_the_catalogue_one(
    db, cart, user, shipping_address, gateway
):
    services.set_cart_item(db, cart, LAPTOP, 1)
    order = services.create_order(db, cart, user)
    bought_at = db.get(Product, LAPTOP).price_cents

    # Somebody edits the catalogue while this customer is still deciding.
    db.get(Product, LAPTOP).price_cents = bought_at + 50_000
    db.flush()
    services.start_checkout(db, order, gateway)

    # They pay what they were shown. The order froze it, and the checkout reads the order.
    assert gateway.starts[0]["lines"][0]["price_data"]["unit_amount"] == bought_at


def test_the_order_remembers_which_checkout_it_was_sent_to(
    db, cart, user, shipping_address, gateway
):
    services.set_cart_item(db, cart, LAPTOP, 1)
    order = services.create_order(db, cart, user)

    services.start_checkout(db, order, gateway)

    # The only thread joining a payment over at Stripe to an order over here. One column,
    # one session - the bet that is lost the moment somebody retries with another card.
    assert order.checkout_session_id == "cs_test_0001"


def test_a_cart_becomes_an_order_even_though_nobody_has_paid(
    db, cart, user, shipping_address
):
    """The uncomfortable consequence, pinned so nobody 'fixes' it by accident."""
    stock_before = db.get(Product, LAPTOP).stock
    token = cart.token
    services.set_cart_item(db, cart, LAPTOP, 2)

    services.create_order(db, cart, user)

    # Stock gone and cart gone, for an order that is not paid. Both were decided in phase
    # 0: the stock is RESERVED, and the pending order is what gets retried - not the cart.
    # What neither of them has yet is the thing that gives the stock back.
    assert db.get(Product, LAPTOP).stock == stock_before - 2
    assert db.get(Cart, token) is None
