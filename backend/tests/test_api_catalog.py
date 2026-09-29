"""The catalog over HTTP. What the unit tests cannot see: status codes, the shape of the
answer, the validation FastAPI does before our code runs, and the absolute image address
that only exists because a request came in."""


def test_the_listing_answers_with_items_and_a_cursor(client):
    response = client.get("/products", params={"limit": 5})

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [1, 2, 3, 4, 5]
    assert body["next_cursor"] == 5


def test_a_product_is_what_the_api_decided_to_expose_and_not_the_table(client):
    product = client.get("/products/1").json()

    assert set(product) == {
        "id", "name", "description", "category", "price_cents", "stock", "image_url"
    }
    # created_at exists in the table and is deliberately not here: the screen does not
    # need it. This test is what stops somebody "helpfully" dumping the whole row.
    assert "created_at" not in product
    # And the category arrives as a name even though the column is a foreign key.
    assert product["category"] == "laptops"


def test_the_image_address_is_absolute_and_built_from_the_request(client):
    product = client.get("/products/1").json()

    # The database stores "/images/product-1.jpg" so the same row works anywhere; turning
    # it into something a browser can ask for is the route's job, and it needs a request
    # to do it - which is why no unit test could have checked this.
    assert product["image_url"].startswith("http://")
    assert product["image_url"].endswith("/images/product-1.jpg")


def test_a_missing_product_is_a_404_with_the_number_that_was_asked_for(client):
    response = client.get("/products/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Product 999 not found"}


def test_nonsense_in_the_query_string_is_refused_before_our_code_runs(client):
    # FastAPI answers these from the type annotations on the route. Worth a test because
    # they are part of the contract: a client that sends limit=0 gets told, not served.
    assert client.get("/products", params={"limit": 0}).status_code == 422
    assert client.get("/products", params={"limit": 101}).status_code == 422
    assert client.get("/products", params={"cursor": -1}).status_code == 422
    assert client.get("/products/abc").status_code == 422


def test_filtering_by_category_over_http(client):
    body = client.get("/products", params={"category": "laptops", "limit": 100}).json()

    assert len(body["items"]) > 0
    assert {item["category"] for item in body["items"]} == {"laptops"}


def test_an_unknown_category_is_an_empty_page_and_not_an_error(client):
    response = client.get("/products", params={"category": "toys"})

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


def test_the_categories_endpoint_is_a_plain_list(client):
    response = client.get("/categories")

    assert response.status_code == 200
    assert [c["name"] for c in response.json()] == [
        "laptops", "monitors", "networking", "peripherals", "storage"
    ]


def test_a_product_with_no_price_changes_answers_an_empty_list_and_not_a_404(client):
    # The decision this endpoint exists to demonstrate. The product is there and its price
    # has never changed: an empty collection is a true, complete answer, so 200.
    response = client.get("/products/1/price-history")

    assert response.status_code == 200
    assert response.json() == []


def test_a_product_that_does_not_exist_answers_404_and_not_an_empty_list(client):
    # The other half, and it only means something next to the test above. Answering [] here
    # would tell a caller who mistyped an id that this product has never changed price.
    response = client.get("/products/999999/price-history")

    assert response.status_code == 404


def test_the_history_over_http_is_a_decision_and_not_the_table(client, db):
    from sqlalchemy import text

    db.execute(text("UPDATE products SET price_cents = 12345 WHERE id = 1"))

    entry = client.get("/products/1/price-history").json()[0]

    assert set(entry) == {"changed_at", "previous_price_cents", "price_cents"}
    assert entry["price_cents"] == 12345
    # No product_id and no row id: the caller named the product in the address and has no
    # use for the primary key of a history row.
    assert "product_id" not in entry
    assert "id" not in entry


def test_the_shop_says_it_is_alive(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_the_frontend_is_allowed_to_call_the_api_and_a_stranger_is_not(client):
    # CORS is configuration, not code, and it is the one thing that stops the shop working
    # in a browser while curl says everything is fine.
    allowed = client.get("/products", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"

    stranger = client.get("/products", headers={"Origin": "https://somewhere-else.example"})
    assert "access-control-allow-origin" not in stranger.headers
