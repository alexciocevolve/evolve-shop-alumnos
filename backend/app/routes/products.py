from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.models import Product
from app.observability import log

router = APIRouter(prefix="/products", tags=["products"])


def product_to_dict(p: Product) -> dict:
    # This function decides what the API exposes. created_at stays out: the screen does
    # not need it. It is a decision, not a dump of the table.
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "category": p.category,
        "price_cents": p.price_cents,
        "stock": p.stock,
        "image_url": p.image_url,
    }


@router.get("")
def list_products(
    category: str | None = None,
    limit: int = Query(12, ge=1, le=100),
    cursor: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    products, next_cursor = services.list_products(db, category, cursor, limit)

    # WHAT THE SHOP DID, not what HTTP did. The middleware already records "GET /products
    # 200 in 4ms", which answers questions about the server. This answers questions about
    # the business, and they are different questions:
    #
    #   · Which categories do people actually browse?
    #   · How often does a filter come back EMPTY? That is somebody looking for something
    #     this shop does not sell, and it is invisible in a 200.
    #   · How deep do people scroll before they stop?
    #
    # None of that can be recovered later from a status code and a path.
    #
    # The fields go under `shop.` because ECS has no vocabulary for a catalogue. Inventing
    # names is fine; inventing them in somebody else's namespace is not, because the day
    # ECS defines `products` the meanings collide and every dashboard has to be redone.
    log.info(
        f"catalogue served: {len(products)} products",
        extra={
            "event.action": "catalogue.list",
            "shop.category": category or "all",
            "shop.products_returned": len(products),
            # The ids, not the whole objects. Enough to tell two pages apart and to join
            # against anything else, without copying the catalogue into the logs.
            "shop.product_ids": [p.id for p in products],
            "shop.product_names": [p.name for p in products],
            "shop.page_size": limit,
            "shop.cursor": cursor,
            "shop.has_next_page": next_cursor is not None,
        },
    )
    return {"items": [product_to_dict(p) for p in products], "next_cursor": next_cursor}


@router.get("/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = services.get_product(db, product_id)
    if product is None:
        # A warning and not an error: nothing is broken. But it is worth having, because
        # a product id that is asked for and does not exist is either a dead link
        # somewhere or somebody walking the ids one by one.
        log.warning(
            f"product {product_id} not found",
            extra={"event.action": "product.miss", "shop.product_id": product_id},
        )
        raise HTTPException(404, f"Product {product_id} not found")

    log.info(
        f"product viewed: {product.name}",
        extra={
            "event.action": "product.view",
            "shop.product_id": product.id,
            "shop.product_name": product.name,
            "shop.category": product.category,
            "shop.price_cents": product.price_cents,
            # The stock AT THE MOMENT IT WAS SHOWN. Not the same as today's: this is what
            # lets somebody ask afterwards whether the thing was already out of stock when
            # the customer was looking at it.
            "shop.stock": product.stock,
        },
    )
    return product_to_dict(product)
