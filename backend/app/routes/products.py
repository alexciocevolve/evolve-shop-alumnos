from urllib.parse import urljoin

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.models import Product

router = APIRouter(prefix="/products", tags=["products"])


def product_to_dict(p: Product, request: Request) -> dict:
    # This function decides what the API exposes. created_at stays out: the screen does
    # not need it. It is a decision, not a dump of the table.
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "category": p.category,
        "price_cents": p.price_cents,
        "stock": p.stock,
        # How to get the image: a plain GET to this address. The database stores a path
        # relative to this server (/images/product-1.svg); the full address is built from
        # the one this request arrived at, so the client never has to know how the server
        # is laid out. An address that is already absolute (an external CDN) passes through.
        "image_url": urljoin(str(request.base_url), p.image_url),
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
    return {"items": [product_to_dict(p, request) for p in products], "next_cursor": next_cursor}


@router.get("/{product_id}")
def get_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    product = services.get_product(db, product_id)
    if product is None:
        raise HTTPException(404, f"Product {product_id} not found")
    return product_to_dict(product, request)
