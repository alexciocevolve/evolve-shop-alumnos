"""Shared setup for every test.

Two decisions worth reading before the tests themselves:

1. The tests run against a SEPARATE database, shop_test, built by running the real
   migrations. Not against the development database, because a test that empties a table
   must not be able to take the class demo with it; and not against a schema made with
   `Base.metadata.create_all`, because then the migrations would quietly stop being true -
   the thing the tests trust would no longer be the thing production runs.

2. Each test runs inside a transaction that is rolled back afterwards, so every test starts
   from the same 36 products and no users. See the `db` fixture for the one subtlety.
"""

import json
import logging
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url

# Before anything from `app` is imported. app.config reads DATABASE_URL at import time, and
# load_dotenv() does not overwrite a variable that is already set, so putting the test
# database here means the whole application points at it for the length of the run.
load_dotenv()
TEST_DATABASE = "shop_test"
_url = make_url(os.environ["DATABASE_URL"])
TEST_URL = _url.set(database=TEST_DATABASE).render_as_string(hide_password=False)
ADMIN_URL = _url.set(database="postgres").render_as_string(hide_password=False)
os.environ["DATABASE_URL"] = TEST_URL

# app.config requires a Stripe key to exist, so one is put here rather than depending on
# whatever .env happens to hold. It is a key-shaped string and nothing more: no test in
# this folder ever reaches Stripe, because every one of them is handed the `pay` fixture
# instead of the real gateway. If a test ever DID reach out, this key would make it
# fail loudly - which is the behaviour we want from an accident like that.
#
# Assigned and not setdefault: the day .env holds a REAL test key, these tests must still
# be unable to charge anything by accident. Overwriting it is cheap insurance.
os.environ["STRIPE_SECRET_KEY"] = "sk_test_the_backend_tests_never_call_stripe"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import payments, services  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.observability import EcsFormatter  # noqa: E402
from app.schemas import AddressIn  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD = "a-long-test-passphrase"


@pytest.fixture(scope="session")
def engine():
    """Create shop_test if it is not there, bring it up to head, and hand back an engine."""
    # CREATE DATABASE cannot run inside a transaction, hence AUTOCOMMIT, and it has to be
    # asked of a database that already exists - "postgres" is the one always present.
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DATABASE}
        ).scalar()
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{TEST_DATABASE}"'))
    admin.dispose()

    # The real migrations, the real seed data. If a downgrade is broken or a model has
    # drifted from its migration, the tests cannot even start - which is the point.
    config = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    command.upgrade(config, "head")

    test_engine = create_engine(TEST_URL)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db(engine):
    """A session whose work is thrown away when the test ends."""
    connection = engine.connect()
    transaction = connection.begin()

    # join_transaction_mode="create_savepoint" is the subtlety. Every service ends in
    # db.commit(), and without this that commit would be real and the data would survive
    # the test. With it, the session works inside a SAVEPOINT: commit() behaves normally
    # as far as the service is concerned, and the outer rollback below still undoes
    # everything. The services are tested exactly as they are written, with no test flag.
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def count_queries(db):
    """Count the SQL statements a piece of code sends, to catch an N+1 that nothing else shows."""
    statements: list[str] = []
    # SAVEPOINT and friends are this harness talking to itself (see the `db` fixture), not
    # work the code under test asked for. Counting them would make the numbers in these
    # tests depend on how the tests are set up, which is the opposite of what they are for.
    NOISE = ("SAVEPOINT", "RELEASE ", "ROLLBACK", "BEGIN", "COMMIT")

    def record(conn, cursor, statement, parameters, context, executemany):
        if not statement.upper().startswith(NOISE):
            statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", record)
    yield statements
    event.remove(db.get_bind(), "before_cursor_execute", record)


@pytest.fixture
def client(db, gateway):
    """The whole application, driven over HTTP, but writing to the test's transaction.

    Overriding get_db is what joins the two: without it the app would open its own
    connection, its commits would be real, and one test's orders would turn up in the next.
    Everything else - the routes, the dependencies, the validation, the status codes - is
    the real thing.

    The gateway is overridden the same way and for a stronger reason: without this line
    every test that buys something would put a real charge through Stripe. It is the same
    seam, used twice, which is the argument for having made the gateway a dependency at
    all. A test that needs a different outcome edits `gateway.says` before asking.
    """

    def use_the_test_session():
        yield db

    app.dependency_overrides[get_db] = use_the_test_session
    app.dependency_overrides[payments.get_gateway] = lambda: gateway
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def shop_logs(caplog):
    """The lines the shop logged during the test, as the JSON Filebeat would ship.

    shop_logs() gives every line; shop_logs("order.create") only those of one event.action.
    """
    caplog.set_level(logging.INFO, logger="shop")
    formatter = EcsFormatter()

    def lines(action: str | None = None) -> list[dict]:
        found = [json.loads(formatter.format(r)) for r in caplog.records if r.name == "shop"]
        return [line for line in found if action is None or line.get("event.action") == action]

    return lines


@pytest.fixture
def auth(db, user):
    """The header a signed-in browser sends."""
    session = services.login(db, user.email, PASSWORD)
    return {"Authorization": f"Bearer {session.token}"}


@pytest.fixture
def other_auth(db, other_user):
    session = services.login(db, other_user.email, "another-test-passphrase")
    return {"Authorization": f"Bearer {session.token}"}


@pytest.fixture
def user(db):
    return services.register_user(db, "ana@example.com", PASSWORD, "Ana Torres")


@pytest.fixture
def other_user(db):
    return services.register_user(db, "beto@example.com", "another-test-passphrase", "Beto Diaz")


@pytest.fixture
def shipping_address(db, user):
    return services.save_address(
        db,
        user,
        is_billing=False,
        data=AddressIn(
            recipient_name="Ana Torres",
            street="Calle Mayor 1",
            city="Madrid",
            postal_code="28013",
        ),
    )


@pytest.fixture
def cart(db):
    return services.create_cart(db)


@pytest.fixture
def gateway():
    """A Stripe that always opens the door, and keeps a note of what it was asked.

    Every test that buys something gets this instead of the real one. Not to go faster: to
    make the tests SAY something. A test that talks to Stripe is testing Stripe's uptime,
    goes red when somebody else has a bad day, and cannot decide what a session comes back
    as. This one can.

    `gateway.starts` is the list of keyword arguments the shop sent, which is how a test
    checks that the lines and the amounts were built from the order and not from the
    client. `gateway.says` is what a later lookup will claim happened, so a test can make
    the buyer's payment succeed, fail, or still be unpaid.
    """

    class Double:
        def __init__(self):
            self.starts = []
            # What fetch() reports back. A test overwrites it before asking.
            self.says = {"payment_status": "paid", "amount_total": None,
                         "payment_intent": "pi_test_0001", "order_id": None}

        def start(self, **asked):
            self.starts.append(asked)
            n = len(self.starts)
            # Ids shaped like Stripe's, so anything that parses them keeps working.
            return payments.Checkout(
                session_id=f"cs_test_{n:04d}",
                url=f"https://checkout.stripe.test/c/pay/cs_test_{n:04d}",
            )

        def fetch(self, session_id):
            return {**self.says, "session_id": session_id}

    return Double()


