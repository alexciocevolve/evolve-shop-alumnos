"""The migrations themselves, run against a database of their own.

The cheapest test in the project and the one that has found the most. Every downgrade in
this repository that Alembic generated wrongly - three of them - would have been caught
here in seconds instead of by hand, months later, at the worst possible moment.

It needs its own database because it empties one, and it cannot use the rollback harness
because CREATE DATABASE and most DDL will not sit inside somebody else's transaction.
"""

import os

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.models import Base
from tests.conftest import ADMIN_URL, BACKEND_DIR, TEST_URL

THROWAWAY = "shop_migrations_test"
THROWAWAY_URL = make_url(TEST_URL).set(database=THROWAWAY).render_as_string(
    hide_password=False
)


def alembic_config() -> Config:
    config = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    return config


def run(*args: str) -> None:
    """Run an Alembic command against the throwaway database.

    env.py reads DATABASE_URL from the environment, so that is what has to be changed -
    and put back, because everything else in the test run points at shop_test.
    """
    previous = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = THROWAWAY_URL
    try:
        getattr(command, args[0])(alembic_config(), *args[1:])
    finally:
        os.environ["DATABASE_URL"] = previous


@pytest.fixture(scope="module")
def empty_database():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        # WITH (FORCE) disconnects anything still attached, so a failed earlier run cannot
        # leave a database behind that nothing can drop.
        connection.execute(text(f'DROP DATABASE IF EXISTS "{THROWAWAY}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{THROWAWAY}"'))

    engine = create_engine(THROWAWAY_URL)
    yield engine

    engine.dispose()
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{THROWAWAY}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def at_head(empty_database):
    """Every test says where it starts from.

    These tests move the database between states, so it is tempting to let them run in
    order and each leave the next one what it needs. That is how a suite ends up where
    running one test on its own fails and nobody can tell whether the code or the test is
    wrong. `upgrade head` is a no-op when it is already there, so this costs nothing.
    """
    run("upgrade", "head")
    return empty_database


def test_every_migration_applies_to_an_empty_database(empty_database):
    run("downgrade", "base")

    run("upgrade", "head")

    with empty_database.connect() as connection:
        # The seed data is part of the migrations, so this also says the hand-written
        # INSERT and the two data-only revisions did their work.
        assert connection.execute(text("SELECT count(*) FROM products")).scalar() == 36
        assert connection.execute(text("SELECT count(*) FROM categories")).scalar() == 5
        extension = connection.execute(
            text("SELECT right(image_url, 4) FROM products WHERE id = 1")
        ).scalar()
        assert extension == ".jpg"


def test_the_models_and_the_migrated_schema_say_the_same_thing(at_head):
    # If somebody changes a model and forgets the migration, it shows up here instead of
    # at the next deployment. This is the `--autogenerate` drift check, asked of Alembic
    # directly rather than by generating a file and reading it.
    #
    # include_schemas is here because of alembic_utils, and the story is worth keeping.
    # Installing it BROKE this test with KeyError: 'include_schemas' - its comparator reads
    # an option that Alembic sets when it runs through env.py and that this test, which
    # calls compare_metadata() itself, was not passing. Adding it is also the upgrade: with
    # the option set, this check now covers the function and the trigger registered in
    # env.py as well as the tables, so a trigger deleted straight from the database is a
    # failure here instead of the silence it used to be.
    with at_head.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "include_schemas": False}
        )
        differences = compare_metadata(context, Base.metadata)

    assert differences == [], f"the models have drifted from the migrations: {differences}"


def test_every_migration_also_undoes_itself_and_the_shop_can_be_rebuilt(at_head):
    run("downgrade", "base")

    with at_head.connect() as connection:
        remaining = connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars().all()

    # Only Alembic's own bookkeeping table is left. Getting this far means all ten
    # downgrades ran, including the three that Alembic wrote in a way that cannot work
    # and that had to be corrected by hand.
    assert remaining == ["alembic_version"]

    run("upgrade", "head")
    with at_head.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM products")).scalar() == 36


def test_going_back_one_step_and_forward_again_keeps_the_data(at_head):
    with at_head.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (email, password_hash, full_name)"
                " VALUES ('step@example.com', 'scrypt$aa$bb', 'Step')"
            )
        )

    run("downgrade", "003b_address_history")
    run("upgrade", "head")

    with at_head.connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM users WHERE email = 'step@example.com'")
        ).scalar() == 1


def test_undoing_the_address_history_keeps_the_address_in_use_and_drops_the_retired_ones(
    at_head,
):
    # The one downgrade in the project that destroys information on purpose, because the
    # older schema has nowhere to keep a history. The test says so out loud, so that
    # nobody discovers it by running it on a real database.
    with at_head.begin() as connection:
        user_id = connection.execute(
            text(
                "INSERT INTO users (email, password_hash, full_name)"
                " VALUES ('hist@example.com', 'scrypt$aa$bb', 'Hist') RETURNING id"
            )
        ).scalar()
        for street, active in [("Old Street", False), ("New Street", True)]:
            connection.execute(
                text(
                    "INSERT INTO addresses (user_id, is_billing, is_active, recipient_name,"
                    " street, city, postal_code) VALUES (:u, false, :a, 'H', :s, 'Madrid', '28001')"
                ),
                {"u": user_id, "a": active, "s": street},
            )

    run("downgrade", "003a_addresses")

    with at_head.connect() as connection:
        streets = connection.execute(
            text("SELECT street FROM addresses WHERE user_id = :u"), {"u": user_id}
        ).scalars().all()

    assert streets == ["New Street"]  # the retired one is gone, and that is documented
