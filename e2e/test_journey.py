"""The whole shop, walked the way a customer walks it, over real HTTP against the real
database. Nothing is mocked, nothing is rolled back: what these tests write is really
written, and the fixtures take it away again afterwards."""

import secrets

import pytest
from sqlalchemy import text


def test_a_customer_can_buy_something_from_start_to_finish(api, shopper, product, cart):
    # 1. Look around. The product this test brought with it is in the catalog like any
    #    other, which also proves the listing is reading the real table.
    listed = api.get(f"/products/{product['id']}").json()
    assert listed["price_cents"] == product["price_cents"]

    # 2. Put two in the cart. The cart exists on the server, not in a browser's memory.
    added = api.put(
        f"/cart/items/{product['id']}", json={"quantity": 2}, headers=cart
    ).json()
    assert added["total_cents"] == product["price_cents"] * 2

    # 3. Say where it is going.
    api.put(
        "/me/addresses/shipping",
        json={
            "recipient_name": "End To End",
            "street": "Calle Mayor 1",
            "city": "Madrid",
            "postal_code": "28013",
        },
        headers=shopper["headers"],
    ).raise_for_status()

    # 4. Pay.
    created = api.post("/orders", headers={**cart, **shopper["headers"]})
    assert created.status_code == 201
    order = created.json()

    # 5. And find it again at the address the server said to look at.
    reread = api.get(created.headers["location"], headers=shopper["headers"]).json()
    assert reread["id"] == order["id"]
    assert reread["customer_email"] == shopper["email"]
    assert reread["shipping_address"]["city"] == "Madrid"
    assert reread["total_cents"] == product["price_cents"] * 2

    # 6. The stock really moved, and the cart really went.
    assert api.get(f"/products/{product['id']}").json()["stock"] == product["stock"] - 2
    assert api.get("/cart", headers=cart).status_code == 404

    # 7. And it is in the customer's own list of orders.
    assert order["id"] in [o["id"] for o in api.get("/orders", headers=shopper["headers"]).json()]


def test_moving_house_does_not_move_an_order_that_was_already_placed(
    api, shopper, product, cart
):
    api.put(f"/cart/items/{product['id']}", json={"quantity": 1}, headers=cart)
    api.put(
        "/me/addresses/shipping",
        json={
            "recipient_name": "End To End",
            "street": "Calle Mayor 1",
            "city": "Madrid",
            "postal_code": "28013",
        },
        headers=shopper["headers"],
    )
    order_id = api.post("/orders", headers={**cart, **shopper["headers"]}).json()["id"]

    # The customer moves.
    api.put(
        "/me/addresses/shipping",
        json={
            "recipient_name": "End To End",
            "street": "Avenida del Puerto 7",
            "city": "Valencia",
            "postal_code": "46021",
        },
        headers=shopper["headers"],
    )

    # The account shows where they live now; the order shows where it was sent. This is
    # the lesson of the checkpoint, proved against a database that really committed both.
    listed = api.get("/me/addresses", headers=shopper["headers"]).json()
    assert [a["city"] for a in listed] == ["Valencia"]

    order = api.get(f"/orders/{order_id}", headers=shopper["headers"]).json()
    assert order["shipping_address"]["city"] == "Madrid"


def test_the_price_on_an_order_does_not_follow_the_catalog(
    api, shopper, product, cart, database
):
    api.put(f"/cart/items/{product['id']}", json={"quantity": 1}, headers=cart)
    api.put(
        "/me/addresses/shipping",
        json={
            "recipient_name": "End To End",
            "street": "Calle Mayor 1",
            "city": "Madrid",
            "postal_code": "28013",
        },
        headers=shopper["headers"],
    )
    order_id = api.post("/orders", headers={**cart, **shopper["headers"]}).json()["id"]

    # The price changes in the shop, by going straight to the database - the way it would
    # really happen, from an import or somebody in psql, not through the API.
    with database.begin() as connection:
        connection.execute(
            text("UPDATE products SET price_cents = 1 WHERE id = :p"), {"p": product["id"]}
        )

    assert api.get(f"/products/{product['id']}").json()["price_cents"] == 1
    order = api.get(f"/orders/{order_id}", headers=shopper["headers"]).json()
    assert order["items"][0]["price_cents"] == product["price_cents"]
    assert order["total_cents"] == product["price_cents"]


@pytest.mark.parametrize(
    "description, headers_key",
    [("with no session at all", None), ("with a token that does not work", "bad")],
)
def test_nobody_can_buy_without_signing_in(api, product, cart, description, headers_key):
    api.put(f"/cart/items/{product['id']}", json={"quantity": 1}, headers=cart)
    headers = dict(cart)
    if headers_key == "bad":
        headers["Authorization"] = "Bearer not-a-real-token"

    response = api.post("/orders", headers=headers)

    assert response.status_code == 401, f"an order was accepted {description}"


def test_one_customer_cannot_read_anothers_order(api, shopper, product, cart, database):
    api.put(f"/cart/items/{product['id']}", json={"quantity": 1}, headers=cart)
    api.put(
        "/me/addresses/shipping",
        json={
            "recipient_name": "End To End",
            "street": "Calle Mayor 1",
            "city": "Madrid",
            "postal_code": "28013",
        },
        headers=shopper["headers"],
    )
    order_id = api.post("/orders", headers={**cart, **shopper["headers"]}).json()["id"]

    # Somebody else, registered the same way anyone would be.
    other_email = f"e2e-other-{secrets.token_hex(4)}@example.com"
    api.post(
        "/users",
        json={"email": other_email, "password": "another-passphrase-here", "full_name": "Other"},
    )
    other_token = api.post(
        "/login", json={"email": other_email, "password": "another-passphrase-here"}
    ).json()["token"]

    try:
        response = api.get(
            f"/orders/{order_id}", headers={"Authorization": f"Bearer {other_token}"}
        )
        # 404 and not 403: a 403 would confirm the order exists, and that is enough to
        # count the shop's orders by asking for one number after another.
        assert response.status_code == 404
        assert response.json() == {"detail": f"Order {order_id} not found"}
    finally:
        with database.begin() as connection:
            user_id = connection.execute(
                text("SELECT id FROM users WHERE email = :e"), {"e": other_email}
            ).scalar()
            connection.execute(text("DELETE FROM sessions WHERE user_id = :u"), {"u": user_id})
            connection.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
