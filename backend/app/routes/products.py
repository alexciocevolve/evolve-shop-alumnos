from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.models import Product, ProductPriceHistory
from app.observability import log
from app.routes.shared import absolute_url

router = APIRouter(prefix="/products", tags=["products"])


def product_to_dict(p: Product, request: Request) -> dict:
    # This function decides what the API exposes. created_at stays out: the screen does
    # not need it. It is a decision, not a dump of the table.
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        # The table changed, this answer does not: the API promised a name and still sends
        # one, read now from the related row. Nothing outside the server has to be rewritten.
        "category": p.category.name,
        "price_cents": p.price_cents,
        "stock": p.stock,
        # How to get the image: a plain GET to this address (see absolute_url).
        "image_url": absolute_url(request, p.image_url),
    }


@router.get("")
def list_products(
    request: Request,
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
    return {"items": [product_to_dict(p, request) for p in products], "next_cursor": next_cursor}


def find_product_or_404(db: Session, product_id: int) -> Product:
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
    return product


def log_product_view(product: Product, source: str) -> None:
    # Two routes report the same event, so the line is written in one place only.
    # `source` says which one it came from: "api" for GET /products/{id}, "modal" for the
    # detail opened in the shop's own page.
    log.info(
        f"product viewed: {product.name}",
        extra={
            "event.action": "product.view",
            "shop.view_source": source,
            "shop.product_id": product.id,
            "shop.product_name": product.name,
            # product.category is the related row now. Logging the object itself would
            # write "<Category object at 0x...>" instead of "laptops".
            "shop.category": product.category.name,
            "shop.price_cents": product.price_cents,
            # The stock AT THE MOMENT IT WAS SHOWN. Not the same as today's: this is what
            # lets somebody ask afterwards whether the thing was already out of stock when
            # the customer was looking at it.
            "shop.stock": product.stock,
        },
    )


@router.get("/{product_id}")
def get_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    product = find_product_or_404(db, product_id)
    log_product_view(product, source="api")
    return product_to_dict(product, request)


# response_class=Response: an empty answer, without the "content-type: application/json"
# header that FastAPI would otherwise add to a body that does not exist.
@router.post("/{product_id}/views", status_code=204, response_class=Response)
def record_product_view(product_id: int, db: Session = Depends(get_db)):
    # The detail modal does not ask the server for anything, because the list already
    # brought the description. Good for speed, but it means the server never finds out
    # that somebody opened a product, and so it cannot log it.
    #
    # So the browser tells the server with this call. Nothing is saved in the database and
    # nothing comes back (204 No Content): the only result is the log line.
    product = find_product_or_404(db, product_id)
    log_product_view(product, source="modal")


def price_change_to_dict(change: ProductPriceHistory) -> dict:
    # No product_id: the caller asked for one product's history and already knows which.
    return {
        "changed_at": change.changed_at,
        "previous_price_cents": change.previous_price_cents,
        "price_cents": change.price_cents,
    }


@router.get("/{product_id}/price-history")
def get_price_history(product_id: int, db: Session = Depends(get_db)):
    history = services.list_price_history(db, product_id)

    # The two answers this endpoint can give, and why they are different:
    #
    #   404      - there is no such product. The address names nothing.
    #   200 []   - the product is there and its price has never changed. That is a true,
    #              complete answer, and an empty collection is not a missing resource.
    #
    # Note that this shop makes the OPPOSITE choice on purpose elsewhere: somebody else's
    # order answers 404 rather than 403, exactly so that a caller CANNOT tell "not yours"
    # from "does not exist". Both come from the same rule - choosing a status code is
    # deciding what the caller is allowed to distinguish - and here we want them to.
    if history is None:
        log.warning(
            f"product {product_id} not found",
            extra={"event.action": "product.miss", "shop.product_id": product_id},
        )
        raise HTTPException(404, f"Product {product_id} not found")

    # Somebody looked at how this price has moved. Put next to product.view, it says how
    # many of the people who open a product also check whether it is a good moment to buy.
    log.info(
        f"price history of product {product_id} read",
        extra={
            "event.action": "product.price_history",
            "shop.product_id": product_id,
            "shop.price_changes_returned": len(history),
        },
    )
    return [price_change_to_dict(change) for change in history]
