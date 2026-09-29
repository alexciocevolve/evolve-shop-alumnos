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

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import services  # noqa: E402
from app.schemas import AddressIn  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
def user(db):
    return services.register_user(db, "ana@example.com", "a-long-test-passphrase", "Ana Torres")


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
