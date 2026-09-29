"""The logs, followed all the way to where somebody will read them.

backend/tests checks what a log line says. These check that the line gets there: out of the
container, through Filebeat, into Elasticsearch, with its fields intact. Nothing in the
shop can see that part of the trip, which is why it is tested from outside.

They wait, because the trip takes a few seconds. Filebeat reads the container's log file
and sends lines in batches, so a line is in Elasticsearch some time after it was written,
never at once.
"""

import secrets
import time

import pytest
from sqlalchemy import text

PATIENCE_SECONDS = 60


def wait_for(elastic, query: dict, expected: int) -> list[dict]:
    """The lines that match `query`, as stored in Elasticsearch, once `expected` have arrived."""
    deadline = time.monotonic() + PATIENCE_SECONDS
    while True:
        hits = elastic.post(
            "/logs-shop-evolve/_search", json={"size": 50, "query": query}
        ).json()["hits"]["hits"]
        if len(hits) >= expected:
            return [hit["_source"] for hit in hits]
        if time.monotonic() > deadline:
            pytest.fail(
                f"After {PATIENCE_SECONDS} s only {len(hits)} of {expected} lines matching "
                f"{query} are in Elasticsearch. Is Filebeat running?"
            )
        time.sleep(2)


def logged_with(elastic, trace_id: str, expected: int) -> list[dict]:
    """The lines of one request, once `expected` of them have arrived."""
    return wait_for(elastic, {"term": {"trace.id": trace_id}}, expected)


def test_a_request_reaches_elasticsearch_with_its_id_and_its_fields(api, elastic):
    # The middleware keeps an X-Request-Id sent by the client, so the test can choose one
    # that nothing else in the world has, and then look for exactly that.
    trace_id = f"e2e-{secrets.token_hex(8)}"
    api.get("/categories", headers={"X-Request-Id": trace_id}).raise_for_status()

    lines = logged_with(elastic, trace_id, expected=2)

    # The line about HTTP and the line about the shop, joined by the same id.
    http = [line for line in lines if line.get("url.path") == "/categories"]
    business = [line for line in lines if line.get("event.action") == "categories.list"]
    assert len(http) == 1 and len(business) == 1
    # Fields, not text: Filebeat unpacked the JSON, so a number is still a number.
    assert http[0]["http.response.status_code"] == 200
    assert business[0]["shop.categories_returned"] >= 1
    # Tagged with where it came from, which is what keeps other projects' logs apart.
    assert http[0]["service.name"] == "shop-api"


def test_what_a_customer_types_as_a_secret_never_reaches_elasticsearch(api, elastic, shopper):
    # Sign in once more with a request id of our own, and wait for that line to arrive.
    # Once it is there, every earlier line of this shopper (registering, the first
    # sign-in) has been shipped too, because Filebeat sends them in order.
    trace_id = f"e2e-{secrets.token_hex(8)}"
    api.post(
        "/login",
        json={"email": shopper["email"], "password": "not-the-right-one"},
        headers={"X-Request-Id": trace_id},
    )
    [failed_login] = [
        line
        for line in logged_with(elastic, trace_id, expected=2)
        if line.get("event.action") == "user.login"
    ]
    assert failed_login["event.reason"] == "wrong_password"

    # Now look for the secrets anywhere, in any field of any line.
    for secret in (shopper["email"], shopper["password"], "not-the-right-one"):
        found = elastic.post(
            "/logs-shop-evolve/_count",
            json={"query": {"multi_match": {"query": secret, "type": "phrase", "lenient": True}}},
        ).json()["count"]
        assert found == 0, f"{secret!r} is in Elasticsearch {found} time(s)"


def test_a_price_changed_behind_the_shops_back_still_shows_up(elastic, database, product):
    # Straight into the database, the way somebody fixes a price from psql. No request, so
    # the shop writes nothing: the only witness is the trigger, which records the change
    # in product_price_history AND writes a line to PostgreSQL's own log (RAISE LOG).
    with database.begin() as connection:
        connection.execute(
            text("UPDATE products SET price_cents = price_cents + 1 WHERE id = :id"),
            {"id": product["id"]},
        )

    expected = (
        f"price change in shop: product {product['id']} "
        f"from {product['price_cents']} to {product['price_cents'] + 1} cents"
    )
    [line] = wait_for(elastic, {"match_phrase": {"message": expected}}, expected=1)
    # It arrives, but as plain text: PostgreSQL does not write JSON, so Filebeat could not
    # turn it into fields and says so. Compare it with the shop's own lines above, where
    # every value is a field that can be filtered and added up.
    assert line["container"]["name"].endswith("-db-1")
    assert "error" in line
