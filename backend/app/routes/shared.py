from urllib.parse import urljoin

from fastapi import Request

from app.models import Address
from app.schemas import ErrorDetail


def error(description: str) -> dict:
    """One entry for a route's `responses=`, describing a failure it really answers with.

    Without these, the generated OpenAPI document lists only 200 and the 422 FastAPI adds
    itself: every 401, 404 and 409 in this shop is raised with HTTPException inside a
    function body, and the generator reads declarations, never bodies.

    Which is worth stating plainly, because it is most of the design: the decisions this
    API took most carefully - 404 rather than 403 for somebody else's order, 404 rather
    than an empty list for a product that does not exist, 409 rather than 400 for a rule
    that said no - were exactly the ones missing from its own documentation.
    """
    return {"model": ErrorDetail, "description": description}


# The three that repeat. Named so that the same failure reads the same way everywhere.
NOT_SIGNED_IN = {
    401: error("No Authorization header, or a token that is unknown or has expired")
}
NO_CART = {404: error("No cart with that X-Cart-Token")}


def absolute_url(request: Request, path: str) -> str:
    """Turn the path stored in the database into the address a browser can ask for.

    The database stores "/images/product-1.jpg", with no host: the same row has to work on
    a laptop and in production. The host comes from the address this request arrived at.
    A path that is already absolute (an external CDN) is returned unchanged.
    """
    return urljoin(str(request.base_url), path)


def address_to_dict(address: Address) -> dict:
    return {
        "id": address.id,
        # The API says "shipping" / "billing" rather than a true/false the reader has to
        # decode. is_active is NOT here: whether the person still uses this address is
        # their business, and an order that points at it does not care either way.
        "kind": "billing" if address.is_billing else "shipping",
        "recipient_name": address.recipient_name,
        "street": address.street,
        "city": address.city,
        "postal_code": address.postal_code,
        "country": address.country,
    }
