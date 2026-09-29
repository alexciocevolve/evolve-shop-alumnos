"""The API's contract, and whether it still says what the code does.

Everywhere else in this suite the rule is "behaviour, never shape". Here the shape IS the
behaviour: the document is what a client reads to find out how to talk to this shop, and a
client cannot read the source.
"""

from app.main import app
from export_openapi import SPEC, render


def test_the_committed_contract_still_matches_the_code():
    # The one that earns its place. FastAPI regenerates this document from the code on
    # every start, so the code can never contradict it - which also means the contract can
    # change without anybody deciding to. Committing the file makes that change arrive as
    # a diff somebody has to approve, and this test is what stops it being skipped.
    assert SPEC.read_text(encoding="utf-8") == render(), (
        "The API contract has changed. If that was intended, run"
        " `python export_openapi.py` and commit the diff - that diff IS the change."
    )


def test_the_failures_this_api_chose_are_in_its_documentation():
    # FastAPI documents what a route declares and never reads a function body, so every
    # error raised with HTTPException is invisible unless it is declared. These four are
    # the decisions this shop argued hardest about; if somebody drops a `responses=`, the
    # test above says "the file changed" and this one says which promise was lost.
    paths = app.openapi()["paths"]

    # Signing in is required to buy, and the rules that can refuse a checkout.
    assert "401" in paths["/orders"]["post"]["responses"]
    assert "409" in paths["/orders"]["post"]["responses"]

    # Somebody else's order: one answer for "not yours" and "does not exist".
    assert "404" in paths["/orders/{order_id}"]["get"]["responses"]

    # And the distinction from cp5: no such product is a 404, while a product that has
    # never changed price is a 200 with an empty list. A caller cannot guess that.
    assert "404" in paths["/products/{product_id}/price-history"]["get"]["responses"]


def test_an_error_says_what_its_body_looks_like():
    not_found = app.openapi()["paths"]["/products/{product_id}"]["get"]["responses"]["404"]

    schema = not_found["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/ErrorDetail")
    # Not decoration: without a declared model the document says a 404 comes back with an
    # unspecified body, and a generated client has nothing to turn the answer into.
