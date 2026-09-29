from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.models import Category
from app.observability import log

router = APIRouter(prefix="/categories", tags=["categories"])


def category_to_dict(c: Category) -> dict:
    return {"id": c.id, "name": c.name}


@router.get("")
def list_categories(db: Session = Depends(get_db)):
    # A plain list, with no pagination: there are five of them and the screen shows them
    # all. Pagination is for what grows without limit, and this does not.
    categories = services.list_categories(db)

    # WHAT THE SHOP OFFERED. The middleware already says "GET /categories 200"; this says
    # which buttons the customer was shown. The list now comes from a table, so it can change
    # without a deploy - a row added or deleted in psql - and this is the only record of
    # WHEN the menu changed and what it held before.
    #
    # An empty list is still a 200, and it leaves the screen with nothing but "All". Nothing
    # has crashed, so nothing else would report it: a warning is the only way anyone hears.
    if not categories:
        log.warning("no categories to show", extra={"event.action": "categories.empty"})
    else:
        log.info(
            f"categories served: {len(categories)}",
            extra={
                "event.action": "categories.list",
                "shop.categories_returned": len(categories),
                "shop.category_names": [c.name for c in categories],
            },
        )
    return [category_to_dict(c) for c in categories]
