from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.models import Cart, Order
from app.observability import fingerprint, log
from app.routes.cart import current_cart

router = APIRouter(prefix="/orders", tags=["orders"])


def order_to_dict(order: Order) -> dict:
    return {
        "id": order.id,
        "customer_email": order.customer_email,
        "status": order.status,
        "total_cents": order.total_cents,
        "created_at": order.created_at.isoformat(),
        "items": [
            {
                "product_id": item.product_id,
                "name": item.product.name,
                "quantity": item.quantity,
                # The price this was bought at, not the price the product has now.
                "price_cents": item.price_cents,
            }
            for item in order.items
        ],
    }


@router.post("", status_code=201)
def create_order(
    response: Response,
    cart: Cart = Depends(current_cart),
    db: Session = Depends(get_db),
):
    # No request body: there is nothing the client gets to decide. Prices, the total and
    # the buyer all come from the server. For now the buyer is always the same placeholder
    # customer (app/config.py); the next checkpoint takes it from the signed-in user.
    # Worked out before the order is placed: placing it deletes the cart, and afterwards
    # there is no token left to take the fingerprint from. With it, the order can be
    # joined to the cart.* lines that came before.
    cart_ref = fingerprint(cart.token)

    try:
        order = services.create_order(db, cart)
    except ValueError as e:
        # This is where the race from session 14 shows up: two people pay for the last
        # unit at the same time, one gets 201 and the other gets this line.
        log.warning(
            "order refused",
            extra={
                "event.action": "order.create",
                "event.outcome": "failure",
                "error.message": str(e),
                "shop.cart_ref": cart_ref,
                "shop.cart_lines": len(cart.items),
            },
        )
        # An empty cart or a line short of stock: the request was understood and the rule
        # says no. That is 409, not 400 and not 404.
        raise HTTPException(409, str(e))

    # The sale itself. The customer's email stays out of the log on purpose: it is
    # personal data, and the order id is enough to find everything else in the database.
    log.info(
        f"order {order.id} placed",
        extra={
            "event.action": "order.create",
            "event.outcome": "success",
            "shop.order_id": order.id,
            "shop.cart_ref": cart_ref,
            "shop.order_total_cents": order.total_cents,
            "shop.order_lines": len(order.items),
            "shop.order_units": sum(item.quantity for item in order.items),
            "shop.product_ids": [item.product_id for item in order.items],
        },
    )
    response.headers["Location"] = f"/orders/{order.id}"
    return order_to_dict(order)


@router.get("/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = services.get_order(db, order_id)
    if order is None:
        # For now any order can be read by its number, because there are no users yet.
        # Somebody asking for 1, 2, 3, 4... one after another would show up here.
        log.warning(
            f"order {order_id} not found",
            extra={"event.action": "order.miss", "shop.order_id": order_id},
        )
        raise HTTPException(404, f"Order {order_id} not found")
    return order_to_dict(order)
