"""The cart over HTTP, where the token lives in a header and each verb has to mean what
its name says."""

LAPTOP = 1
MOUSE = 3


def header(token: str) -> dict:
    return {"X-Cart-Token": token}


def test_creating_a_cart_answers_201_and_hands_back_the_token(client):
    response = client.post("/cart")

    # 201 and not 200: this call creates something. The token is what the browser has to
    # keep, and it is in the body because there is nowhere else for it to be.
    assert response.status_code == 201
    body = response.json()
    assert body["items"] == []
    assert body["total_cents"] == 0
    assert len(body["token"]) >= 40


def test_a_cart_line_carries_what_the_screen_needs_and_nothing_more(client):
    token = client.post("/cart").json()["token"]

    body = client.put(
        f"/cart/items/{LAPTOP}", json={"quantity": 2}, headers=header(token)
    ).json()

    line = body["items"][0]
    assert set(line) == {
        "product_id", "name", "image_url", "price_cents", "quantity", "subtotal_cents"
    }
    assert line["subtotal_cents"] == line["price_cents"] * 2  # worked out on the server
    assert body["total_cents"] == line["subtotal_cents"]


def test_the_same_put_twice_leaves_the_same_cart(client):
    token = client.post("/cart").json()["token"]

    client.put(f"/cart/items/{LAPTOP}", json={"quantity": 2}, headers=header(token))
    second = client.put(f"/cart/items/{LAPTOP}", json={"quantity": 2}, headers=header(token))

    assert second.status_code == 200
    assert [(i["product_id"], i["quantity"]) for i in second.json()["items"]] == [(LAPTOP, 2)]


def test_a_quantity_of_zero_is_refused_by_the_schema(client):
    token = client.post("/cart").json()["token"]

    response = client.put(f"/cart/items/{LAPTOP}", json={"quantity": 0}, headers=header(token))

    # Removing a line is what DELETE is for. Field(ge=1) says so before our code runs.
    assert response.status_code == 422


def test_asking_for_more_than_there_is_answers_409_with_the_reason(client):
    token = client.post("/cart").json()["token"]

    # Product 2 has no stock in the seed data.
    response = client.put("/cart/items/2", json={"quantity": 1}, headers=header(token))

    # 409 and not 400: the request was understood, the rule says no.
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_a_product_that_does_not_exist_is_a_404_even_with_a_good_cart(client):
    token = client.post("/cart").json()["token"]

    response = client.put("/cart/items/999", json={"quantity": 1}, headers=header(token))

    assert response.status_code == 404
    assert response.json() == {"detail": "Product 999 not found"}


def test_removing_a_line_that_is_not_there_says_which_one(client):
    token = client.post("/cart").json()["token"]

    response = client.delete(f"/cart/items/{MOUSE}", headers=header(token))

    assert response.status_code == 404
    assert response.json() == {"detail": f"Product {MOUSE} is not in the cart"}


def test_removing_a_line_gives_back_the_cart_without_it(client):
    token = client.post("/cart").json()["token"]
    client.put(f"/cart/items/{LAPTOP}", json={"quantity": 1}, headers=header(token))
    client.put(f"/cart/items/{MOUSE}", json={"quantity": 1}, headers=header(token))

    body = client.delete(f"/cart/items/{MOUSE}", headers=header(token)).json()

    assert [i["product_id"] for i in body["items"]] == [LAPTOP]


def test_a_token_that_names_no_cart_is_a_404(client):
    assert client.get("/cart", headers=header("not-a-real-token")).status_code == 404


def test_with_no_token_at_all_there_is_nothing_to_look_at(client):
    # The header is required, so this is FastAPI refusing a malformed request rather than
    # the shop answering a question about somebody's cart.
    assert client.get("/cart").status_code == 422


def test_one_cart_token_cannot_reach_another_cart(client):
    mine = client.post("/cart").json()["token"]
    theirs = client.post("/cart").json()["token"]
    client.put(f"/cart/items/{LAPTOP}", json={"quantity": 1}, headers=header(theirs))

    assert client.get("/cart", headers=header(mine)).json()["items"] == []
