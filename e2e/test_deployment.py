"""Things that are only true when the shop is really assembled and running.

Every one of these passes in backend/tests by construction - the app is imported there, so
of course it exists. Here they can fail, and the ways they fail are the ways a deployment
actually goes wrong: a container that did not start, migrations that never ran, a CORS
setting that is right in the file and wrong in the environment, images that nobody mounted.
"""

import httpx2
import pytest

from conftest import FRONTEND


def test_the_backend_is_up_and_says_so(api):
    assert api.get("/health").json() == {"status": "ok"}


def test_the_migrations_really_ran_against_the_real_database(api):
    # Not a schema check: if the tables were missing this would be a 500. It is the
    # cheapest possible proof that `alembic upgrade head` happened at start-up.
    body = api.get("/products", params={"limit": 3}).json()

    assert len(body["items"]) == 3
    assert body["items"][0]["category"] == "laptops"  # the categories table exists and is filled


def test_the_frontend_is_being_served(web):
    try:
        response = web.get("/")
    except httpx2.RequestError as reason:
        pytest.fail(f"Nothing is answering at {FRONTEND}: {reason}")

    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text
    # The page is a shell: whatever fills it comes from the script it points at.
    assert "/src/main.tsx" in response.text or "/assets/" in response.text


def test_the_browser_would_be_allowed_to_call_the_api_from_the_frontend(api):
    # The one that matters, and the one no in-process test can prove: the API and the
    # frontend are on different origins, and CORS_ORIGINS has to name the address the
    # frontend is REALLY served from. Right in the code and wrong in the environment is
    # a shop that looks fine to curl and is broken in every browser.
    response = api.get("/products", params={"limit": 1}, headers={"Origin": FRONTEND})

    assert response.headers.get("access-control-allow-origin") == FRONTEND


def test_a_stranger_is_still_not_allowed(api):
    response = api.get(
        "/products", params={"limit": 1}, headers={"Origin": "https://somewhere-else.example"}
    )

    assert "access-control-allow-origin" not in response.headers


def test_the_preflight_a_browser_sends_before_a_put_is_answered(api):
    # Before PUT /cart/items/... the browser asks permission with OPTIONS. If this is not
    # answered, nothing can ever be added to a cart, however well the PUT itself works.
    response = api.request(
        "OPTIONS",
        "/cart/items/1",
        headers={
            "Origin": FRONTEND,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "x-cart-token,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_the_images_the_api_promises_can_actually_be_fetched(api):
    product = api.get("/products/1").json()

    # The address is built by the server and the file is served by the server, but from a
    # folder mounted into the container. Nothing in-process can tell whether that mount
    # exists - this is the only test that would notice it missing.
    image = api.get(product["image_url"])

    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/")
    assert len(image.content) > 0


def test_a_missing_image_is_a_404_and_not_a_page(api):
    assert api.get("/images/does-not-exist.jpg").status_code == 404


def test_the_api_documents_itself(api):
    # /docs is how anybody working on the shop finds out what it offers.
    paths = api.get("/openapi.json").json()["paths"]

    assert "/products" in paths
    assert "/orders" in paths
