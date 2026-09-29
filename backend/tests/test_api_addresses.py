"""Addresses over HTTP. The thing to notice is what is missing from every path: an id."""

MADRID = {
    "recipient_name": "Ana Torres",
    "street": "Calle Mayor 1",
    "city": "Madrid",
    "postal_code": "28013",
}
VALENCIA = {
    "recipient_name": "Ana Torres",
    "street": "Avenida del Puerto 7",
    "city": "Valencia",
    "postal_code": "46021",
}


def test_saving_an_address_answers_with_it(client, auth):
    response = client.put("/me/addresses/shipping", json=MADRID, headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "shipping"
    assert body["city"] == "Madrid"
    assert body["country"] == "ES"  # the default, and upper case


def test_only_the_two_kinds_that_exist_are_accepted(client, auth):
    # Declared as a Literal on the route, so FastAPI refuses anything else before our code
    # runs, and the two allowed values turn up in the generated documentation.
    assert client.put("/me/addresses/home", json=MADRID, headers=auth).status_code == 422
    assert client.put("/me/addresses/shipping", json=MADRID, headers=auth).status_code == 200
    assert client.put("/me/addresses/billing", json=MADRID, headers=auth).status_code == 200


def test_a_country_that_is_not_two_letters_is_refused(client, auth):
    payload = {**MADRID, "country": "Spain"}

    assert client.put("/me/addresses/shipping", json=payload, headers=auth).status_code == 422


def test_the_second_save_replaces_what_is_listed_without_losing_the_first(client, auth):
    first = client.put("/me/addresses/shipping", json=MADRID, headers=auth).json()

    second = client.put("/me/addresses/shipping", json=VALENCIA, headers=auth).json()

    # A new row, not an edit: the id changes, and that is the whole point.
    assert second["id"] != first["id"]
    listed = client.get("/me/addresses", headers=auth).json()
    assert [a["city"] for a in listed] == ["Valencia"]


def test_shipping_comes_before_billing_every_time(client, auth):
    client.put("/me/addresses/billing", json=VALENCIA, headers=auth)
    client.put("/me/addresses/shipping", json=MADRID, headers=auth)

    listed = client.get("/me/addresses", headers=auth).json()

    # Saved in the other order, listed in this one: the account page must not shuffle.
    assert [a["kind"] for a in listed] == ["shipping", "billing"]


def test_deleting_answers_204_and_then_404(client, auth):
    client.put("/me/addresses/shipping", json=MADRID, headers=auth)

    assert client.delete("/me/addresses/shipping", headers=auth).status_code == 204
    assert client.get("/me/addresses", headers=auth).json() == []

    response = client.delete("/me/addresses/shipping", headers=auth)
    assert response.status_code == 404
    assert response.json() == {"detail": "No shipping address to delete"}


def test_addresses_need_a_session(client):
    assert client.get("/me/addresses").status_code == 401
    assert client.put("/me/addresses/shipping", json=MADRID).status_code == 401
    assert client.delete("/me/addresses/shipping").status_code == 401


def test_one_person_never_sees_anothers_addresses(client, auth, other_auth):
    client.put("/me/addresses/shipping", json=MADRID, headers=auth)

    assert client.get("/me/addresses", headers=other_auth).json() == []


def test_no_route_takes_an_address_id(client, auth):
    # There is no /me/addresses/{id} to guess at. Every route works from the session, so
    # there is no number to change in order to reach somebody else's address. Asked of the
    # published documentation, which is the contract, rather than of FastAPI's internals.
    paths = client.get("/openapi.json").json()["paths"]
    address_paths = sorted(p for p in paths if "address" in p)

    assert address_paths == ["/me/addresses", "/me/addresses/{kind}"]
