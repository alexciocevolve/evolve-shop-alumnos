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

PATIENCE_SECONDS = 60


def logged_with(elastic, trace_id: str, expected: int) -> list[dict]:
    """The lines of one request, as stored in Elasticsearch, once `expected` have arrived."""
    deadline = time.monotonic() + PATIENCE_SECONDS
    while True:
        hits = elastic.post(
            "/logs-shop-evolve/_search",
            json={"size": 50, "query": {"term": {"trace.id": trace_id}}},
        ).json()["hits"]["hits"]
        if len(hits) >= expected:
            return [hit["_source"] for hit in hits]
        if time.monotonic() > deadline:
            pytest.fail(
                f"After {PATIENCE_SECONDS} s only {len(hits)} of {expected} lines with "
                f"trace.id {trace_id} are in Elasticsearch. Is Filebeat running?"
            )
        time.sleep(2)


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
