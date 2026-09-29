"""product images

Revision ID: 001a_product_images
Revises: 001_products
Create Date: 2026-09-19 14:43:27.385192

"""
from typing import Sequence, Union

from alembic import op
# No `import sqlalchemy as sa` here, unlike 001_products: this revision only runs SQL
# through op.execute() and never builds a column or a type, so it would be an unused import.


# revision identifiers, used by Alembic.
revision: str = '001a_product_images'
down_revision: Union[str, Sequence[str], None] = '001_products'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade data."""
    # Written ENTIRELY BY HAND, nothing here comes from `--autogenerate`. The schema does not
    # change (image_url is still a NOT NULL TEXT column), so autogenerate would have produced
    # an empty migration: it compares schemas, not data. What changes is the DATA. The seed
    # products of 001_products point at an external site (picsum.photos); from now on each
    # one points at its own file, served by this API under /images (see data/images).
    # The value is a path relative to the server, not a full address: the API builds the
    # full URL from the address each request arrived at, so the database does not hard-code
    # a host and the same data works on localhost and in production.
    # The WHERE clause only touches rows still on the old external URL, so a product that
    # someone has already pointed at another image is left alone.
    op.execute("""
        UPDATE products
        SET image_url = '/images/product-' || id || '.svg'
        WHERE image_url LIKE 'https://picsum.photos/seed/product-%'
    """)


def downgrade() -> None:
    """Downgrade data."""
    # The exact reverse, by hand as well: back to the external placeholder photos.
    op.execute("""
        UPDATE products
        SET image_url = 'https://picsum.photos/seed/product-' || id || '/400/300'
        WHERE image_url LIKE '/images/product-%'
    """)
