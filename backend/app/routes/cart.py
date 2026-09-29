from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.models import Cart
from app.observability import fingerprint, log
from app.routes.shared import NO_CART, absolute_url, error
from app.schemas import QuantityIn

router = APIRouter(prefix="/cart", tags=["cart"])


def current_cart(
    request: Request,
    x_cart_token: str = Header(),
    db: Session = Depends(get_db),
) -> Cart:
    # The token travels in a header, not in the path: a cart address that appears in the
    # browser bar ends up copied into a chat, and then it is someone else's cart.
    cart = services.get_cart(db, x_cart_token)
    if cart is None:
        # Usually harmless: a browser kept a token for a cart that is gone (the order was
        # placed, or the database was reset). Many of them in a row, each one different,
        # would be somebody trying tokens at random.
        log.warning(
            "cart not found",
            extra={"event.action": "cart.miss", "shop.cart_ref": fingerprint(x_cart_token)},
        )
        raise HTTPException(404, "Cart not found")
    return cart


def cart_summary(cart: Cart) -> dict:
    # The fields every cart log carries, so that any single line can be read on its own.
    # The token itself is never logged, only its fingerprint (see observability.py).
    return {
        "shop.cart_ref": fingerprint(cart.token),
        "shop.cart_lines": len(cart.items),
        "shop.cart_units": sum(item.quantity for item in cart.items),
        "shop.cart_total_cents": services.cart_total_cents(cart),
    }


def cart_to_dict(cart: Cart, request: Request) -> dict:
    return {
        "token": cart.token,
        "items": [
            {
                "product_id": item.product_id,
                "name": item.product.name,
                "image_url": absolute_url(request, item.product.image_url),
                # Today's price and the line total, both worked out on the server.
                "price_cents": item.product.price_cents,
                "quantity": item.quantity,
                "subtotal_cents": item.product.price_cents * item.quantity,
            }
            for item in cart.items
        ],
        "total_cents": services.cart_total_cents(cart),
    }


@router.post("", status_code=201)
def create_cart(request: Request, db: Session = Depends(get_db)):
    # 201 and not 200: this call CREATES something. The token in the answer is what the
    # browser has to keep and send back in the header from now on.
    cart = services.create_cart(db)
    log.info("cart created", extra={"event.action": "cart.create", **cart_summary(cart)})
    return cart_to_dict(cart, request)


@router.get("", responses=NO_CART)
def get_cart(request: Request, cart: Cart = Depends(current_cart)):
    return cart_to_dict(cart, request)


@router.put(
    "/items/{product_id}",
    responses={
        404: error("No cart with that X-Cart-Token, or no product with that id"),
        # 409 and not 400: the request was understood perfectly and a RULE said no. The
        # difference matters to a client, which can retry a 409 with a smaller quantity.
        409: error("Not enough stock for the quantity asked for"),
    },
)
def set_cart_item(
    product_id: int,
    body: QuantityIn,
    request: Request,
    cart: Cart = Depends(current_cart),
    db: Session = Depends(get_db),
):
    # PUT, not POST: it SETS the quantity to a value rather than adding to it. Sending it
    # twice leaves the same cart, so a retry after a dropped connection is harmless.
    try:
        updated = services.set_cart_item(db, cart, product_id, body.quantity)
    except ValueError as e:
        # The customer asked for more units than there are. They see the message on the
        # screen; the log keeps it. Many of these for the same product mean that people
        # want more of it than the shop has.
        log.warning(
            f"cart: not enough stock for product {product_id}",
            extra={
                "event.action": "cart.item.set",
                # ECS has a field for "did it work?". Filtering by it gives every refusal
                # at once, whatever the action was.
                "event.outcome": "failure",
                "error.message": str(e),
                "shop.cart_ref": fingerprint(cart.token),
                "shop.product_id": product_id,
                "shop.quantity": body.quantity,
            },
        )
        raise HTTPException(409, str(e))  # the rule broken is stock, not a missing thing
    if updated is None:
        log.warning(
            f"product {product_id} not found",
            extra={"event.action": "product.miss", "shop.product_id": product_id},
        )
        raise HTTPException(404, f"Product {product_id} not found")

    log.info(
        f"cart: product {product_id} set to {body.quantity}",
        extra={
            "event.action": "cart.item.set",
            "event.outcome": "success",
            "shop.product_id": product_id,
            "shop.quantity": body.quantity,
            **cart_summary(updated),
        },
    )
    return cart_to_dict(updated, request)


@router.delete(
    "/items/{product_id}",
    responses={404: error("No cart with that X-Cart-Token, or that product is not in it")},
)
def remove_cart_item(
    product_id: int,
    request: Request,
    cart: Cart = Depends(current_cart),
    db: Session = Depends(get_db),
):
    if not services.remove_cart_item(db, cart, product_id):
        raise HTTPException(404, f"Product {product_id} is not in the cart")

    updated = services.get_cart(db, cart.token)
    # A product taken out of the cart is interesting on its own: put next to the
    # cart.item.set lines, it shows what people considered and then did not buy.
    log.info(
        f"cart: product {product_id} removed",
        extra={"event.action": "cart.item.remove", "shop.product_id": product_id, **cart_summary(updated)},
    )
    return cart_to_dict(updated, request)
