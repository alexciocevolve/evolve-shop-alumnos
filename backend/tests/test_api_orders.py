"""Checkout over HTTP, and the two holes this checkpoint closed: orders placed by nobody,
and orders readable by anybody."""

LAPTOP = 1


def filled_cart(client, quantity: int = 1) -> dict:
    token = client.post("/cart").json()["token"]
    headers = {"X-Cart-Token": token}
    client.put(f"/cart/items/{LAPTOP}", json={"quantity": quantity}, headers=headers)
    return headers


def test_nobody_can_place_an_order_without_signing_in(client):
    cart = filled_cart(client)

    assert client.post("/orders", headers=cart).status_code == 401


def test_a_token_that_does_not_work_is_refused_rather_than_served_as_a_guest(client):
    cart = filled_cart(client)

    response = client.post("/orders", headers={**cart, "Authorization": "Bearer nope"})

    # Somebody tried to say who they were and failed. Quietly treating them as a guest
    # would hide an expired session instead of showing it.
    assert response.status_code == 401


def test_an_order_needs_an_address_to_go_to(client, auth):
    cart = filled_cart(client)  # `auth` has no address: shipping_address is not requested

    response = client.post("/orders", headers={**cart, **auth})

    assert response.status_code == 409
    assert response.json() == {
        "detail": "A shipping address is required before placing an order"
    }


def test_placing_an_order_answers_201_with_where_to_find_it(client, auth, shipping_address):
    cart = filled_cart(client, quantity=2)

    response = client.post("/orders", headers={**cart, **auth})

    assert response.status_code == 201
    # The Location header is how a client finds the thing that was just created, without
    # having to build the address itself.
    assert response.headers["location"] == f"/orders/{response.json()['id']}"


def test_the_order_carries_the_buyer_and_the_address(client, auth, shipping_address, user):
    cart = filled_cart(client)

    body = client.post("/orders", headers={**cart, **auth}).json()

    assert body["customer_email"] == user.email
    # This line did not change in objective 16, and that is the whole point of it. Since
    # the first commit of the shop it asserted "paid" on an order nobody had paid for -
    # phase 0 found it pinning a lie. Now a card is charged before the transaction commits,
    # so the word is finally true and the test never had to move. What changed is the
    # meaning, not the code, which is the most honest kind of progress there is.
    assert body["status"] == "paid"
    assert body["shipping_address"]["street"] == "Calle Mayor 1"
    assert body["shipping_address"]["kind"] == "shipping"
    # is_active is the customer's business and no concern of an order.
    assert "is_active" not in body["shipping_address"]


def test_an_empty_cart_is_a_409(client, auth, shipping_address):
    token = client.post("/cart").json()["token"]

    response = client.post("/orders", headers={"X-Cart-Token": token, **auth})

    assert response.status_code == 409
    assert response.json() == {"detail": "The cart is empty"}


def test_the_cart_is_gone_once_it_has_become_an_order(client, auth, shipping_address):
    cart = filled_cart(client)

    client.post("/orders", headers={**cart, **auth})

    assert client.get("/cart", headers=cart).status_code == 404


def test_an_order_cannot_be_read_without_signing_in(client, auth, shipping_address):
    cart = filled_cart(client)
    order_id = client.post("/orders", headers={**cart, **auth}).json()["id"]

    # Before this checkpoint this answered 200, with the customer's email and street.
    assert client.get(f"/orders/{order_id}").status_code == 401


def test_somebody_elses_order_is_a_404_and_not_a_403(client, auth, other_auth, shipping_address):
    cart = filled_cart(client)
    order_id = client.post("/orders", headers={**cart, **auth}).json()["id"]

    response = client.get(f"/orders/{order_id}", headers=other_auth)

    # 403 would confirm that this order exists, and that is enough to count the shop's
    # orders by asking for one number after another. The sentence is the same as for an
    # order that was never placed.
    assert response.status_code == 404
    assert response.json() == {"detail": f"Order {order_id} not found"}
    assert client.get("/orders/99999", headers=other_auth).json() == {
        "detail": "Order 99999 not found"
    }


def test_the_list_of_orders_holds_only_your_own(client, auth, other_auth, shipping_address):
    cart = filled_cart(client)
    client.post("/orders", headers={**cart, **auth})

    assert len(client.get("/orders", headers=auth).json()) == 1
    assert client.get("/orders", headers=other_auth).json() == []
    assert client.get("/orders").status_code == 401


def test_the_whole_journey_from_an_empty_shop_to_a_confirmed_order(client, auth, shipping_address):
    # The end-to-end path, in the order a person actually walks it.
    token = client.post("/cart").json()["token"]
    cart = {"X-Cart-Token": token}

    client.put(f"/cart/items/{LAPTOP}", json={"quantity": 1}, headers=cart)
    client.put("/cart/items/3", json={"quantity": 2}, headers=cart)
    client.delete("/cart/items/3", headers=cart)
    before = client.get("/cart", headers=cart).json()
    assert [i["product_id"] for i in before["items"]] == [LAPTOP]

    created = client.post("/orders", headers={**cart, **auth})
    order = client.get(created.headers["location"], headers=auth).json()

    assert order["total_cents"] == before["total_cents"]
    assert [i["product_id"] for i in order["items"]] == [LAPTOP]


def test_a_refused_card_answers_402_and_creates_nothing(client, auth, shipping_address, declining_pay):
    """A decline is its own answer, not a generic "no"."""
    from app import payments
    from app.main import app

    # The client fixture installs a gateway that always agrees; this swaps it for one that
    # refuses. Same seam, opposite answer - which is the argument for the seam existing.
    app.dependency_overrides[payments.get_gateway] = lambda: declining_pay

    cart = filled_cart(client)
    response = client.post("/orders", headers={**cart, **auth})

    # 402 and not 409: a client that wants to offer another card can tell from the number
    # alone, without reading English. A 409 from this endpoint could equally be an empty
    # cart, a line short of stock or a missing address.
    assert response.status_code == 402
    # Stripe's own wording, which is already written for a person.
    assert "insufficient funds" in response.json()["detail"].lower()
    # And nothing survived: no order, and the cart is still there to try again with.
    assert client.get("/orders", headers=auth).json() == []
    assert client.get("/cart", headers=cart).status_code == 200
