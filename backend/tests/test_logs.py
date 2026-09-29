"""What the shop writes in its logs, and above all what it must never write.

A log line is read by more people than the database, and it is copied to more places, so
it deserves tests like any other output of the program. These tests run the services and
read what they logged, turned into the same JSON that ends up in Elasticsearch.
"""

import json
import logging

import pytest

from app import services
from app.observability import EcsFormatter, fingerprint

PASSWORD = "a-long-test-passphrase"


@pytest.fixture
def shop_logs(caplog):
    """The lines the shop logged during the test, as the JSON Filebeat would ship."""
    caplog.set_level(logging.INFO, logger="shop")
    formatter = EcsFormatter()

    def lines(action: str | None = None) -> list[dict]:
        found = [json.loads(formatter.format(r)) for r in caplog.records if r.name == "shop"]
        return [line for line in found if action is None or line.get("event.action") == action]

    return lines


def test_a_fingerprint_is_short_always_the_same_and_does_not_contain_the_secret():
    token = "this-is-a-cart-token-nobody-should-read"

    assert fingerprint(token) == fingerprint(token)
    assert fingerprint(token) != fingerprint(token + "x")
    assert len(fingerprint(token)) == 12
    assert "cart-token" not in fingerprint(token)


def test_a_wrong_password_is_logged_with_the_reason_and_the_user(db, user, shop_logs):
    services.login(db, user.email, "wrong-password")

    [line] = shop_logs("user.login")
    assert line["event.outcome"] == "failure"
    assert line["event.reason"] == "wrong_password"
    assert line["user.id"] == user.id
    assert line["log.level"] == "warning"


def test_an_unknown_email_is_logged_by_its_fingerprint_only(db, shop_logs):
    services.login(db, "nobody@example.com", "wrong-password")

    [line] = shop_logs("user.login")
    assert line["event.reason"] == "unknown_email"
    assert line["shop.email_ref"] == fingerprint("nobody@example.com")
    assert "nobody@example.com" not in json.dumps(line)


def test_no_password_reaches_the_logs_neither_the_right_one_nor_the_wrong_one(db, user, shop_logs):
    services.login(db, user.email, "wrong-password")
    services.login(db, user.email, PASSWORD)

    # First make sure there is something to look at: with no lines at all, the asserts
    # below would pass without proving anything.
    assert len(shop_logs("user.login")) == 2
    everything = json.dumps(shop_logs())
    assert "wrong-password" not in everything
    assert PASSWORD not in everything
    # The email is personal data: the user is named by user.id instead.
    assert user.email not in everything


def test_a_session_is_logged_by_its_fingerprint_and_never_by_its_token(db, user, shop_logs):
    session = services.login(db, user.email, PASSWORD)

    [line] = shop_logs("user.login")
    assert line["event.outcome"] == "success"
    assert line["shop.session_ref"] == fingerprint(session.token)
    # Whoever has the token IS the user for the next 24 hours.
    assert session.token not in json.dumps(shop_logs())
