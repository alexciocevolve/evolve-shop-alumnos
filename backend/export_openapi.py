"""Write the API's OpenAPI document to openapi.json.

    python export_openapi.py

FastAPI builds this document from the code every time it starts, so it can never be out
of date with the code. What it CAN be is out of date with what anybody agreed to, because
nobody agreed to anything: it is a byproduct, produced after the fact, and it changes
silently the moment a route changes.

Writing it into the repository turns it into something else. The contract now arrives in
a pull request as a diff that a person has to read and approve, and `test_openapi.py`
refuses to pass while the file and the code disagree. That is as close as a code-first
framework gets to the API-first idea of agreeing on the contract first - not the same
thing, but it does stop the contract changing without anybody noticing.

Importing app.main reads .env through app/config.py, so this works from a terminal in
backend/; in CI, set DATABASE_URL instead. No connection is opened: building the document
only reads the routes.
"""

import json
from pathlib import Path

from app.main import app

SPEC = Path(__file__).parent / "openapi.json"


def render() -> str:
    """The exact text of the file, so the exporter and the test cannot disagree on format."""
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    SPEC.write_text(render(), encoding="utf-8")
    print(f"Wrote {SPEC}")
