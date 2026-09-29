"""record price changes with a trigger

Revision ID: 004a_price_trigger
Revises: 004_price_history
Create Date: 2026-09-20 00:28:40.081788

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004a_price_trigger'
down_revision: Union[str, Sequence[str], None] = '004_price_history'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # EVERY LINE OF THIS MIGRATION IS HANDWRITTEN, and the empty migration that
    # --autogenerate produced here is the whole lesson of the checkpoint. Not an error,
    # not a warning: `pass`. Alembic compares the models against the database, a trigger
    # is in neither, so there is nothing to compare and nothing to say.

    op.execute(
        """
        CREATE FUNCTION record_price_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            INSERT INTO product_price_history (product_id, previous_price_cents, price_cents)
            VALUES (NEW.id, OLD.price_cents, NEW.price_cents);
            RAISE LOG 'price change in %: product % from % to % cents',
                current_database(), NEW.id, OLD.price_cents, NEW.price_cents;
            RETURN NEW;
        END;
        $$
        """
    )
    # The function is WHAT to do. It is an object of its own: it has a name, it can be
    # called by anything, and it exists whether or not any trigger uses it. OLD and NEW are
    # the row before and after the UPDATE, and they are the reason a trigger can record a
    # transition at all - by the time application code sees the row, the old value is gone.
    #
    # RAISE LOG writes one line to PostgreSQL's own log, which is the only log that sees
    # this happen: a price changed from psql never passes through the shop's code, so the
    # shop has nothing to say about it. The line goes to the db container's output and
    # Filebeat already reads that container, so it reaches Kibana next to the shop's own
    # lines. LOG is a level for the server's log only: whoever ran the UPDATE sees nothing.
    #
    # current_database() because that log is ONE for the whole server: the tests change
    # prices too, in shop_test, and without the name their lines look exactly like real ones.
    #
    # RETURN NEW is ignored in an AFTER trigger. It is written because the day this becomes
    # a BEFORE trigger it would stop being ignored, and a function that returns nothing
    # would silently cancel the UPDATE.

    op.execute(
        """
        CREATE TRIGGER trg_products_price_change
        AFTER UPDATE OF price_cents ON products
        FOR EACH ROW
        WHEN (OLD.price_cents IS DISTINCT FROM NEW.price_cents)
        EXECUTE FUNCTION record_price_change()
        """
    )
    # The trigger is WHEN to do it, and the three qualifiers are the difference between a
    # useful history and a table full of noise:
    #
    #   AFTER            - only record changes that actually committed to the row.
    #   OF price_cents   - restocking a product is not a price change. Without this the
    #                      function would run on every UPDATE of the row.
    #   WHEN (...)       - saving the same price again is not a change either.
    #
    # IS DISTINCT FROM and not <>, because <> answers NULL when either side is NULL, the
    # WHEN would not be true, and a price going to or from NULL would go unrecorded. Here
    # price_cents is NOT NULL so it cannot happen - which is exactly why it is worth
    # writing correctly now, while the reason is visible, rather than after the column
    # becomes nullable in two years and the history quietly develops holes.


def downgrade() -> None:
    """Downgrade schema."""
    # Autogenerate left `pass` here, and `pass` is a working downgrade in the only sense
    # Alembic can check: it runs, it reports success, and the version table moves back.
    # Reproduced before writing these two lines, because it is the fourth broken downgrade
    # of this project and the only one that does not announce itself:
    #
    #   1. `alembic downgrade 003c_orders_user` -> both revisions undone, no error at all.
    #   2. The table is gone. The trigger and the function are still there.
    #   3. Hours or days later, somebody changes a price - through psql, through the
    #      shop, through anything - and gets:
    #
    #        ERROR:  relation "product_price_history" does not exist
    #        CONTEXT:  PL/pgSQL function record_price_change() line 3 at SQL statement
    #
    # An error naming a table that the schema at 003c is not supposed to have, raised by a
    # function nobody remembers, at a moment unrelated to the migration that caused it. And
    # reads keep working, so the catalogue looks healthy and only writing a price fails.
    #
    # The order matters: the trigger uses the function, so PostgreSQL refuses to drop the
    # function while the trigger still exists.
    op.execute("DROP TRIGGER trg_products_price_change ON products")
    op.execute("DROP FUNCTION record_price_change()")
