from urllib.parse import urljoin

from fastapi import Request


def absolute_url(request: Request, path: str) -> str:
    """Turn the path stored in the database into the address a browser can ask for.

    The database stores "/images/product-1.jpg", with no host: the same row has to work on
    a laptop and in production. The host comes from the address this request arrived at.
    A path that is already absolute (an external CDN) is returned unchanged.
    """
    return urljoin(str(request.base_url), path)
