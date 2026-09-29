"""End-to-end tests: the shop as it really runs, over the network.

The rule that makes these different from backend/tests, and it is worth saying out loud:

    NOTHING HERE IMPORTS THE APPLICATION.

No `from app import ...` anywhere. These tests only speak HTTP and SQL, exactly like a
browser and a database client would. A test that imports the code it is testing can pass
while the containers are misconfigured, the migrations never ran, CORS is wrong or the
images are not being served - which is the whole set of things this layer exists to catch.

They run against the DEVELOPMENT database, because that is what the running shop uses. So
they bring their own product and their own customer, and take both away afterwards: the 36
seed products are never touched, and no stock is left changed after a run.
"""

import base64
import os
import secrets

import httpx2
import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

BACKEND = os.environ.get("E2E_BACKEND_URL", "http://localhost:8000")
FRONTEND = os.environ.get("E2E_FRONTEND_URL", "http://localhost:5173")
# Elasticsearch as seen from this machine. ELASTIC_HOST in .env is the name Filebeat uses
# inside Docker's network, which means nothing out here.
ELASTIC = os.environ.get("E2E_ELASTIC_URL", "http://127.0.0.1:9200")
PASSWORD = "a-long-end-to-end-passphrase"


@pytest.fixture(scope="session")
def api():
    """An HTTP client pointed at the running shop, or a clear skip if it is not up."""
    client = httpx2.Client(base_url=BACKEND, timeout=10)
    try:
        client.get("/health").raise_for_status()
    except Exception as reason:  # noqa: BLE001 - any failure means the same thing
        pytest.skip(
            f"The shop is not running at {BACKEND} ({reason}). "
            "Start it with `docker compose up -d` and try again."
        )
    yield client
    client.close()


@pytest.fixture(scope="session")
def web():
    """An HTTP client pointed at the frontend.

    Deliberately no skip here, unlike `api`. If nothing at all is running, the `api`
    fixture has already skipped the run with "start it with docker compose up" - the
    person simply forgot. But a backend that answers while the frontend does not is a
    half-deployed shop, and that is a failure to report, not a test to quietly pass over.
    """
    client = httpx2.Client(base_url=FRONTEND, timeout=10)
    yield client
    client.close()


@pytest.fixture(scope="session")
def elastic():
    """An HTTP client for the Elasticsearch the logs end up in, or a clear skip.

    It skips instead of failing because Elasticsearch is not part of this shop: it is the
    shared `elastic-real` set from session 24, with a life of its own. The shop working
    while the logging system is down is exactly the arrangement the README describes.
    """
    key = os.environ.get("ELASTIC_API_KEY", "")
    if ":" not in key:
        pytest.skip("No ELASTIC_API_KEY in .env (see .env.example), so the logs cannot be read.")
    # .env keeps the key as id:api_key, the form Filebeat wants. Elasticsearch's HTTP API
    # wants the same thing in base64 after "ApiKey".
    encoded = base64.b64encode(key.encode()).decode()
    client = httpx2.Client(
        base_url=ELASTIC, headers={"Authorization": f"ApiKey {encoded}"}, timeout=10
    )
    try:
        client.get("/logs-shop-evolve/_count").raise_for_status()
    except Exception as reason:  # noqa: BLE001 - any failure means the same thing
        pytest.skip(
            f"Elasticsearch is not answering at {ELASTIC} ({reason}). Start "
            "../python-demo/sesion-24/elastic-real with `docker compose up -d` and try again."
        )
    yield client
    client.close()


@pytest.fixture(scope="session")
def database():
    """A connection to the real database, used only to set up and clear away."""
    engine = create_engine(os.environ["DATABASE_URL"])
    yield engine
    engine.dispose()


@pytest.fixture
def product(database):
    """A product of this test's own, so the shop's own stock is never touched.

    Buying one of the 36 seed products would mean putting its stock back afterwards, and
    the day that step fails the class demo quietly starts from a shop that is wrong.
    """
    with database.begin() as connection:
        product_id = connection.execute(
            text(
                "INSERT INTO products (name, description, category_id, price_cents, stock,"
                " image_url) SELECT 'End-to-end test product', 'Created and removed by the"
                " end-to-end tests.', id, 12345, 3, '/images/product-1.jpg' FROM categories"
                " WHERE name = 'laptops' RETURNING id"
            )
        ).scalar()

    yield {"id": product_id, "price_cents": 12345, "stock": 3}

    with database.begin() as connection:
        _remove_product(connection, product_id)


@pytest.fixture
def shopper(api, database, product):
    """A customer of this test's own, registered through the API like anybody else."""
    # A different email every run, so two runs in a row do not collide on the unique
    # constraint, and a leftover from a crashed run cannot be mistaken for this one.
    email = f"e2e-{secrets.token_hex(4)}@example.com"
    api.post(
        "/users", json={"email": email, "password": PASSWORD, "full_name": "End To End"}
    ).raise_for_status()
    token = api.post("/login", json={"email": email, "password": PASSWORD}).json()["token"]

    yield {"email": email, "password": PASSWORD, "headers": {"Authorization": f"Bearer {token}"}}

    # Plain SQL, in an order the foreign keys allow. There is no endpoint that deletes an
    # account, and there should not be one just to make the tests tidy.
    with database.begin() as connection:
        user_id = connection.execute(
            text("SELECT id FROM users WHERE email = :e"), {"e": email}
        ).scalar()
        if user_id is not None:
            connection.execute(
                text(
                    "DELETE FROM order_items WHERE order_id IN"
                    " (SELECT id FROM orders WHERE user_id = :u)"
                ),
                {"u": user_id},
            )
            connection.execute(text("DELETE FROM orders WHERE user_id = :u"), {"u": user_id})
            connection.execute(text("DELETE FROM sessions WHERE user_id = :u"), {"u": user_id})
            connection.execute(
                text("DELETE FROM addresses WHERE user_id = :u"), {"u": user_id}
            )
            connection.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})


def _remove_product(connection, product_id: int) -> None:
    connection.execute(
        text("DELETE FROM order_items WHERE product_id = :p"), {"p": product_id}
    )
    connection.execute(text("DELETE FROM cart_items WHERE product_id = :p"), {"p": product_id})
    connection.execute(text("DELETE FROM products WHERE id = :p"), {"p": product_id})


@pytest.fixture
def cart(api, database):
    """A cart, created the way the browser creates one: by asking for it."""
    token = api.post("/cart").json()["token"]

    yield {"X-Cart-Token": token}

    # A cart that became an order was deleted by the server; one that did not is still
    # sitting there. Leaving it would mean every run adds a little more rubbish to the
    # real database, which is exactly the habit these tests must not teach.
    with database.begin() as connection:
        connection.execute(text("DELETE FROM cart_items WHERE cart_token = :t"), {"t": token})
        connection.execute(text("DELETE FROM carts WHERE token = :t"), {"t": token})
