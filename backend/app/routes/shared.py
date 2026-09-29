from urllib.parse import urljoin

from fastapi import Request

from app.models import Address


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
