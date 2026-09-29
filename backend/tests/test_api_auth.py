"""Registering and signing in over HTTP, and the things that must never appear in an
answer no matter what is asked."""

from tests.conftest import PASSWORD


def test_registering_answers_201_with_the_account_and_no_secrets(client):
    response = client.post(
        "/users",
        json={"email": "nueva@example.com", "password": PASSWORD, "full_name": "Nueva"},
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "full_name", "created_at"}
    # Neither the hash nor the password, under any name. This is the assertion that would
    # catch somebody adding the model straight to the answer.
    assert "password" not in response.text
    assert "scrypt" not in response.text


def test_the_same_email_twice_is_a_409_that_names_it(client):
    payload = {"email": "ana@example.com", "password": PASSWORD, "full_name": "Ana"}
    client.post("/users", json=payload)

    response = client.post("/users", json=payload)

    assert response.status_code == 409
    assert response.json() == {"detail": "Email ana@example.com is already registered"}


def test_the_registration_form_is_checked_before_anything_is_stored(client):
    too_short = {"email": "x@example.com", "password": "short", "full_name": "X"}
    not_an_email = {"email": "not-an-email", "password": PASSWORD, "full_name": "X"}
    no_name = {"email": "y@example.com", "password": PASSWORD, "full_name": ""}

    assert client.post("/users", json=too_short).status_code == 422
    assert client.post("/users", json=not_an_email).status_code == 422
    assert client.post("/users", json=no_name).status_code == 422


def test_signing_in_hands_back_a_token_and_nothing_else(client, user):
    response = client.post("/login", json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 200
    assert set(response.json()) == {"token"}


def test_a_wrong_password_and_an_unknown_email_give_the_same_401(client, user):
    wrong = client.post("/login", json={"email": user.email, "password": "nope"})
    unknown = client.post("/login", json={"email": "nobody@example.com", "password": "nope"})

    assert wrong.status_code == unknown.status_code == 401
    # Word for word the same. Anything else turns the sign-in form into a way of finding
    # out who shops here.
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}


def test_me_needs_a_token_and_says_so_the_same_way_every_time(client, auth):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    # A header that forgot the word Bearer is not a different kind of failure.
    assert client.get("/me", headers={"Authorization": "just-a-token"}).status_code == 401
    assert client.get("/me", headers={"Authorization": ""}).status_code == 401

    assert client.get("/me", headers=auth).status_code == 200


def test_the_401_never_explains_which_part_was_wrong(client):
    body = client.get("/me", headers={"Authorization": "Bearer nope"}).json()

    # Unknown token and expired token get the same sentence: the difference is of no use
    # to whoever is asking.
    assert body == {"detail": "Invalid or expired token"}


def test_me_describes_the_signed_in_person(client, auth, user):
    body = client.get("/me", headers=auth).json()

    assert body["email"] == user.email
    assert body["full_name"] == "Ana Torres"
    assert "password_hash" not in body


def test_signing_out_answers_204_and_the_token_stops_working(client, auth):
    response = client.post("/logout", headers=auth)

    assert response.status_code == 204
    assert response.content == b""  # 204 means "done, nothing to say"
    assert client.get("/me", headers=auth).status_code == 401


def test_signing_out_without_a_token_is_a_401_and_not_a_silent_success(client):
    assert client.post("/logout").status_code == 401
