"""The log lines written by the routes, checked over HTTP the way a browser would cause them.

Same idea as test_logs.py: what a line must say, and above all what it must never say. The
difference is that here the secrets arrive the way they do in real life, inside headers and
request bodies, which is exactly where they slip into a log by accident.
"""

import json

from sqlalchemy import text

LAPTOP = 1


def filled_cart(client) -> dict:
    token = client.post("/cart").json()["token"]
    headers = {"X-Cart-Token": token}
    client.put(f"/cart/items/{LAPTOP}", json={"quantity": 1}, headers=headers)
    return headers


def test_every_request_gets_one_line_and_its_id_goes_back_to_the_client(client, shop_logs):
    response = client.get("/categories")

    [http_line] = [line for line in shop_logs() if line.get("url.path") == "/categories"]
    assert http_line["http.response.status_code"] == 200
    # The id a customer can quote when something goes wrong...
    assert http_line["trace.id"] == response.headers["X-Request-Id"]
    # ...and the one that joins the HTTP line to what the shop did while serving it.
    [business_line] = shop_logs("categories.list")
    assert business_line["trace.id"] == http_line["trace.id"]


def test_the_cart_token_never_reaches_the_logs(client, shop_logs):
    cart = filled_cart(client)
    client.delete(f"/cart/items/{LAPTOP}", headers=cart)
    client.get("/cart", headers={"X-Cart-Token": "a-token-that-does-not-exist"})

    assert shop_logs("cart.item.set") and shop_logs("cart.miss")
    everything = json.dumps(shop_logs())
    assert cart["X-Cart-Token"] not in everything
    assert "a-token-that-does-not-exist" not in everything


def test_an_order_is_logged_with_who_bought_it_but_not_their_email(
    client, auth, user, shipping_address, shop_logs
):
    order = client.post("/orders", headers={**filled_cart(client), **auth}).json()

    [line] = [line for line in shop_logs("order.create") if line["event.outcome"] == "success"]
    assert line["shop.order_id"] == order["id"]
    assert line["user.id"] == user.id
    assert line["shop.shipping_address_id"] == shipping_address.id
    assert user.email not in json.dumps(shop_logs())


def test_asking_for_somebody_elses_order_is_logged_with_who_asked(
    client, auth, other_auth, other_user, shipping_address, shop_logs
):
    order_id = client.post("/orders", headers={**filled_cart(client), **auth}).json()["id"]

    # The answer says nothing: the same 404 as for an order that does not exist.
    assert client.get(f"/orders/{order_id}", headers=other_auth).status_code == 404
    # The log says everything.
    [line] = shop_logs("order.miss")
    assert line["user.id"] == other_user.id
    assert line["shop.order_id"] == order_id


def test_an_address_is_logged_by_its_country_and_nothing_that_points_to_a_house(
    client, auth, shop_logs
):
    address = {
        "recipient_name": "Ana Torres",
        "street": "Calle Mayor 1",
        "city": "Madrid",
        "postal_code": "28013",
    }
    client.put("/me/addresses/shipping", json=address, headers=auth)

    [line] = shop_logs("user.address.save")
    assert line["shop.address_country"] == "ES"
    everything = json.dumps(shop_logs())
    for private in address.values():
        assert private not in everything


def test_registering_signing_in_and_out_leaves_no_password_token_or_email(client, shop_logs):
    credentials = {"email": "nueva@example.com", "password": "a-long-new-passphrase"}
    client.post("/users", json={**credentials, "full_name": "Nueva"})
    token = client.post("/login", json=credentials).json()["token"]
    client.post("/logout", headers={"Authorization": f"Bearer {token}"})

    assert shop_logs("user.register") and shop_logs("user.login") and shop_logs("user.logout")
    everything = json.dumps(shop_logs())
    for secret in (credentials["password"], token, credentials["email"]):
        assert secret not in everything


def test_reading_a_price_history_is_logged_with_how_many_changes_it_had(client, db, shop_logs):
    # Straight into the table, like a price fixed from psql: the trigger adds the history row.
    db.execute(text("UPDATE products SET price_cents = price_cents + 1 WHERE id = :id"), {"id": LAPTOP})

    assert len(client.get(f"/products/{LAPTOP}/price-history").json()) == 1

    [line] = shop_logs("product.price_history")
    assert line["shop.product_id"] == LAPTOP
    assert line["shop.price_changes_returned"] == 1


def test_a_healthy_health_check_leaves_no_line(client, shop_logs):
    # The container is asked every few seconds whether it is alive. Logging every "yes"
    # would drown the lines that matter; only a failing check would be worth a line.
    assert client.get("/health").status_code == 200
    assert client.get("/categories").status_code == 200

    paths = [line.get("url.path") for line in shop_logs()]
    assert "/health" not in paths
    assert "/categories" in paths
