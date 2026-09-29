"""Registering and signing in, including the two things the answer must not reveal."""

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app import services
from app.models import UserSession

PASSWORD = "a-long-test-passphrase"


def test_registering_stores_a_hash_and_never_the_password(db):
    user = services.register_user(db, "nueva@example.com", PASSWORD, "Nueva")

    assert user.password_hash.startswith("scrypt$")
    # Not anywhere in the row, under any column: the strongest form of the assertion.
    row = db.execute(
        text("SELECT * FROM users WHERE id = :id"), {"id": user.id}
    ).mappings().one()
    assert PASSWORD not in " ".join(str(value) for value in row.values())


def test_two_people_with_the_same_password_do_not_look_the_same_in_the_table(db):
    first = services.register_user(db, "a@example.com", PASSWORD, "A")
    second = services.register_user(db, "b@example.com", PASSWORD, "B")
    assert first.password_hash != second.password_hash


def test_an_email_can_only_be_registered_once(db):
    assert services.register_user(db, "ana@example.com", PASSWORD, "Ana") is not None
    # None rather than an exception, and decided by the unique constraint rather than by
    # asking first: between the question and the INSERT, two people both pass.
    assert services.register_user(db, "ana@example.com", "different-passphrase", "Otra") is None


def test_signing_in_with_the_right_password_gives_a_session(db, user):
    session = services.login(db, user.email, PASSWORD)

    assert session is not None
    assert len(session.token) >= 40
    assert session.user_id == user.id
    # A session that lasts forever is a password that never expires.
    remaining = session.expires_at - datetime.now(timezone.utc)
    assert timedelta(hours=23) < remaining <= timedelta(hours=24)


def test_a_wrong_password_and_an_unknown_email_are_answered_the_same_way(db, user):
    # Both None, so the route cannot accidentally say which it was. Saying "no account
    # with that email" turns the sign-in form into a way of finding out who shops here.
    assert services.login(db, user.email, "wrong-password") is None
    assert services.login(db, "nobody@example.com", "wrong-password") is None


def test_the_password_is_checked_even_when_there_is_no_such_user(db):
    # The timing half of the same idea. Measuring milliseconds is flaky, so what is
    # asserted is the reason it holds: the work is done either way. scrypt takes ~50 ms,
    # which is what would otherwise make "no such account" come back noticeably sooner.
    start = time.perf_counter()
    services.login(db, "nobody@example.com", "wrong-password")
    unknown_email = time.perf_counter() - start

    assert unknown_email > 0.01, "answered too fast to have hashed anything"


def test_a_session_token_names_its_owner(db, user):
    session = services.login(db, user.email, PASSWORD)
    assert services.get_user_by_session(db, session.token).id == user.id


def test_an_unknown_token_is_nobody(db):
    assert services.get_user_by_session(db, "not-a-real-token") is None


def test_an_expired_session_stops_working_although_its_row_is_still_there(db, user):
    session = services.login(db, user.email, PASSWORD)
    session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    assert services.get_user_by_session(db, session.token) is None
    # What makes a session valid is the date, not the existence of the row.
    assert db.get(UserSession, session.token) is not None


def test_signing_out_deletes_the_session_everywhere_and_not_just_in_one_browser(db, user):
    session = services.login(db, user.email, PASSWORD)

    services.logout(db, session.token)

    assert services.get_user_by_session(db, session.token) is None
    assert db.get(UserSession, session.token) is None


def test_signing_in_twice_gives_two_sessions_that_both_work(db, user):
    # A phone and a laptop are not the same session, and signing in on one must not throw
    # the other out.
    first = services.login(db, user.email, PASSWORD)
    second = services.login(db, user.email, PASSWORD)

    assert first.token != second.token
    assert services.get_user_by_session(db, first.token) is not None
    assert services.get_user_by_session(db, second.token) is not None


def test_deleting_a_user_takes_their_sessions_with_them(db, user):
    services.login(db, user.email, PASSWORD)
    db.delete(user)
    db.commit()

    assert db.query(UserSession).count() == 0  # ON DELETE CASCADE, not tidying up by hand
