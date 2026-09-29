"""What the shop writes in its logs, and above all what it must never write.

A log line is read by more people than the database, and it is copied to more places, so
it deserves tests like any other output of the program. These tests run the services and
read what they logged, turned into the same JSON that ends up in Elasticsearch (the
`shop_logs` fixture in conftest.py). The lines written by the routes are checked through
the API in test_api_logs.py.
"""

import json

from sqlalchemy import create_engine

import app.main
from app import services
from app.observability import fingerprint

PASSWORD = "a-long-test-passphrase"


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


def test_start_up_says_where_the_database_is_and_that_it_answers(shop_logs):
    app.main.say_whether_the_database_answers()

    [line] = shop_logs("startup.database")
    assert line["event.outcome"] == "success"
    assert line["shop.database"] == "shop_test"


def test_an_unreachable_database_is_reported_without_its_password(monkeypatch, shop_logs):
    # Port 1: nothing listens there, so the connection is refused at once. This is the
    # render.yaml region mistake in miniature - a shop pointed at a database it cannot reach.
    unreachable = create_engine("postgresql+psycopg://shop:do-not-log-me@127.0.0.1:1/shop")
    monkeypatch.setattr(app.main, "engine", unreachable)
    # 2 s is the shortest wait libpq accepts. Without a limit this test once took 130 s on a
    # machine where a closed port does not refuse but stays silent, which is exactly the
    # case the limit in main.py is there for.
    monkeypatch.setattr(app.main, "STARTUP_CHECK_TIMEOUT_SECONDS", 2)

    app.main.say_whether_the_database_answers()

    [line] = shop_logs("startup.database")
    assert line["event.outcome"] == "failure"
    assert line["log.level"] == "error"
    assert line["destination.address"] == "127.0.0.1"
    assert "do-not-log-me" not in json.dumps(line)
