import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic_utils.pg_function import PGFunction
from alembic_utils.pg_trigger import PGTrigger
from alembic_utils.replaceable_entity import register_entities

from alembic import context
from app.config import with_driver
from app.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# The connection URL comes from the environment (.env), not from alembic.ini. It is read
# HERE and not imported from app/config.py, because the migration tests point Alembic at a
# throwaway database by swapping this variable around the call: an imported constant would
# have been frozen at import time and would have migrated the wrong database.
#
# What does come from app/config.py is with_driver(), so the migrations connect exactly the
# way the application does. On a managed host the URL arrives as `postgresql://...` and has
# to name a driver before SQLAlchemy can use it - without this, the shop would start and
# the migrations would not.
load_dotenv()
config.set_main_option("sqlalchemy.url", with_driver(os.environ["DATABASE_URL"]))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
#
# disable_existing_loggers=False: by default fileConfig switches off every logger that
# already exists. When the migrations run in the same process as the shop (the tests do
# exactly that), the "shop" logger would go silent from then on, with no error at all.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The models are the source of truth: `--autogenerate` compares this metadata
# with the real database and writes the difference as a migration.
target_metadata = Base.metadata

# And here is the second source of truth, which exists because Base.metadata cannot hold
# everything a PostgreSQL database contains. A function and a trigger are not tables, not
# columns and not constraints, so they are nowhere in the models - which is why plain
# autogenerate produced an empty migration for revision 004a and why the drift check said
# "no changes" with the trigger deleted.
#
# alembic_utils adds a second comparison. These objects are declared here, it asks the
# database what it really has, and the difference goes into the migration like any other.

record_price_change = PGFunction(
    schema="public",
    signature="record_price_change()",
    definition="""
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        INSERT INTO product_price_history (product_id, previous_price_cents, price_cents)
        VALUES (NEW.id, OLD.price_cents, NEW.price_cents);
        RAISE LOG 'price change in %: product % from % to % cents',
            current_database(), NEW.id, OLD.price_cents, NEW.price_cents;
        RETURN NEW;
    END;
    $$
    """,
)

trg_products_price_change = PGTrigger(
    schema="public",
    signature="trg_products_price_change",
    on_entity="public.products",
    definition="""
    AFTER UPDATE OF price_cents ON public.products
    FOR EACH ROW
    WHEN (OLD.price_cents IS DISTINCT FROM NEW.price_cents)
    EXECUTE FUNCTION record_price_change()
    """,
)

register_entities([record_price_change, trg_products_price_change])

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # also detect column type changes, not only added/removed columns
            # And default changes. Off by default, and the third thing in this project that
            # --autogenerate could not see: first triggers (004a, fixed with alembic_utils),
            # then entities in the drift test (include_schemas), now defaults.
            #
            # Found by accident: changing orders.status from "paid" to "pending_payment"
            # produced an EMPTY migration, and the drift test stayed green while the model
            # and the database disagreed. That particular change was then postponed - it
            # belongs to the phase that introduces the state machine, not to the one that
            # only makes "paid" true - but the hole it exposed is real and is closed here.
            #
            # It has a reputation for false positives, because it compares the rendered SQL
            # of each default and `now()` does not always render the same way. Measured on
            # this schema before switching it on: the only differences it found were real.
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
