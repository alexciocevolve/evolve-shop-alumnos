"""product images as photographs

Revision ID: 001b_product_images_jpg
Revises: 001a_product_images
Create Date: 2026-09-19 16:12:04.118427

"""
from typing import Sequence, Union

from alembic import op
# Same as 001a: only op.execute(), so sqlalchemy is not imported.


# revision identifiers, used by Alembic.
revision: str = '001b_product_images_jpg'
down_revision: Union[str, Sequence[str], None] = '001a_product_images'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade data."""
    # Written ENTIRELY BY HAND, like 001a: the schema does not change (image_url is still a
    # NOT NULL TEXT column), only the DATA, and `--autogenerate` compares schemas, so it would
    # have produced an empty migration. 001a pointed every product at a generated placeholder
    # drawing, `/images/product-<id>.svg`; each one is now a real photograph of that kind of
    # product, `/images/product-<id>.jpg`, sitting next to it in data/images.
    # The WHERE clause compares against the exact value 001a wrote, so it only touches rows
    # that are still on their own generated drawing: a product someone has already repointed
    # at another image keeps it. The .svg files stay on disk so `downgrade` still serves them.
    op.execute("""
        UPDATE products
        SET image_url = '/images/product-' || id || '.jpg'
        WHERE image_url = '/images/product-' || id || '.svg'
    """)


def downgrade() -> None:
    """Downgrade data."""
    # The exact reverse, by hand as well: back to the generated drawings.
    op.execute("""
        UPDATE products
        SET image_url = '/images/product-' || id || '.svg'
        WHERE image_url = '/images/product-' || id || '.jpg'
    """)
