from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import payments, services
from app.db import get_db
from app.models import Cart, Order, User
from app.observability import fingerprint, log
from app.routes.cart import current_cart
from app.routes.shared import NOT_SIGNED_IN, address_to_dict, error
from app.routes.users import current_user

router = APIRouter(prefix="/orders", tags=["orders"])


def order_to_dict(order: Order) -> dict:
    return {
        "id": order.id,
        "customer_email": order.customer_email,
        "status": order.status,
        "total_cents": order.total_cents,
        "created_at": order.created_at.isoformat(),
        # The address as it was when the order was placed. It reads from the related row
        # and still shows the old street after the customer moves, because that row is
        # never edited - moving house writes a new row and retires this one.
        "shipping_address": (
            address_to_dict(order.shipping_address) if order.shipping_address else None
        ),
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


@router.post(
    "",
    status_code=201,
    responses={
        **NOT_SIGNED_IN,
        404: error("No cart with that X-Cart-Token"),
        402: error("The card was refused. Nothing was charged and no order was created"),
        409: error(
            "The cart is empty, a line is short of stock, "
            "or the account has no shipping address yet"
        ),
    },
)
def create_order(
    response: Response,
    cart: Cart = Depends(current_cart),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    pay=Depends(payments.get_gateway),
):
    # Signing in is required: without a token this is a 401 and no order is created.
    # There is still no request body. Prices, the total, the buyer and the shipping
    # address are all decided by the server; the browser only says who it is, with its
    # token. A client allowed to name an address id could name somebody else's.
    #
    # Worked out before the order is placed: placing it deletes the cart, and afterwards
    # there is no token left to take the fingerprint from. With it, the order can be
    # joined to the cart.* lines that came before.
    cart_ref = fingerprint(cart.token)

    try:
        order = services.create_order(db, cart, user, pay)
    except ValueError as e:
        # This is where the race from session 14 shows up: two people pay for the last
        # unit at the same time, one gets 201 and the other gets this line. It is also
        # where "no shipping address yet" ends up, for anybody who skips the screen.
        log.warning(
            "order refused",
            extra={
                "event.action": "order.create",
                "event.outcome": "failure",
                "error.message": str(e),
                "user.id": user.id,
                "shop.cart_ref": cart_ref,
                "shop.cart_lines": len(cart.items),
            },
        )
        # An empty cart or a line short of stock: the request was understood and the rule
        # says no. That is 409, not 400 and not 404.
        raise HTTPException(409, str(e))
    except payments.PaymentDeclined as e:
        # 402, the one status code that was reserved for exactly this and that almost
        # nobody ever gets to use. It is a defensible choice rather than an obvious one:
        # 409 would also fit, because a refused card is a rule saying no like any other.
        #
        # 402 wins here for one reason - it tells the caller WHICH kind of no, without
        # reading the sentence. A 409 from this endpoint could be an empty cart, missing
        # stock or a missing address, and a client that wants to offer another card has to
        # parse English to find out. 402 means "the money did not happen" and nothing else.
        #
        # Stripe's own wording goes straight through, because it is already written for a
        # person: "Your card has insufficient funds."
        #
        # Logged as an order that did not happen, like the 409s above, so that one search
        # (order.create, failure) still finds every purchase that went wrong. The details of
        # what Stripe said are in the payment.charge line written by the service.
        log.warning(
            "order refused: payment declined",
            extra={
                "event.action": "order.create",
                "event.outcome": "failure",
                "event.reason": "payment_declined",
                "error.message": str(e),
                "user.id": user.id,
                "shop.cart_ref": cart_ref,
            },
        )
        raise HTTPException(402, str(e))

    # The sale itself. The customer's email stays out of the log on purpose: it is
    # personal data, and user.id plus the order id are enough to find everything else in
    # the database.
    log.info(
        f"order {order.id} placed",
        extra={
            "event.action": "order.create",
            "event.outcome": "success",
            "user.id": user.id,
            "shop.order_id": order.id,
            "shop.cart_ref": cart_ref,
            "shop.order_total_cents": order.total_cents,
            "shop.order_lines": len(order.items),
            "shop.order_units": sum(item.quantity for item in order.items),
            "shop.product_ids": [item.product_id for item in order.items],
            # The address row it was sent to, not its contents. With the id, the address
            # can be looked up in the database by whoever is allowed to; in the log it
            # tells nothing about where anybody lives.
            "shop.shipping_address_id": order.shipping_address_id,
            # Stripe's name for this payment. Not a secret: it is useless without the key,
            # and it is exactly what somebody types into the Stripe dashboard to find it.
            "shop.payment_intent_id": order.payment_intent_id,
        },
    )
    response.headers["Location"] = f"/orders/{order.id}"
    return order_to_dict(order)


@router.get("", responses=NOT_SIGNED_IN)
def list_orders(user: User = Depends(current_user), db: Session = Depends(get_db)):
    orders = services.list_orders(db, user)
    # How many orders the person has when they look at their account. Put next to
    # order.create, it shows who comes back to check on an order after buying.
    log.info(
        f"user {user.id} listed their orders",
        extra={"event.action": "order.list", "user.id": user.id, "shop.orders_returned": len(orders)},
    )
    return [order_to_dict(order) for order in orders]


@router.get(
    "/{order_id}",
    responses={
        **NOT_SIGNED_IN,
        # Documented as one answer on purpose, because it IS one answer. Splitting it into
        # "not found" and "not yours" in the documentation would hand back exactly the
        # information the 404 was chosen to withhold.
        404: error("No such order, OR it belongs to somebody else - the same answer to both"),
    },
)
def get_order(
    order_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    order = services.get_order(db, order_id, user)
    if order is None:
        # The customer gets the same 404 for "no such order" and "not yours". The log can
        # say more, because it knows who asked: one user.id asking for 1, 2, 3, 4... one
        # after another is somebody trying to read other people's orders.
        log.warning(
            f"order {order_id} not found",
            extra={"event.action": "order.miss", "user.id": user.id, "shop.order_id": order_id},
        )
        # 404 and not 403, and the same sentence for "no such order" and "not yours".
        # A 403 would confirm that order 42 exists, which is enough to count the shop's
        # orders by asking for one number after another.
        raise HTTPException(404, f"Order {order_id} not found")
    return order_to_dict(order)
