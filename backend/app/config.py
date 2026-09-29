import os
from pathlib import Path

from dotenv import load_dotenv

# Everything the app reads from the environment lives in this one file.
load_dotenv()  # finds .env by walking up from this file, so it works from any directory

def with_driver(url: str) -> str:
    """Name the driver in the connection URL, whatever shape the host handed it over in.

    Managed databases give you a URL in the shape the psql command line wants, so Render
    hands over `postgresql://...` (and Heroku still hands over the older `postgres://`).
    SQLAlchemy needs to be told which driver to speak it with - `postgresql+psycopg://` -
    and without that it looks for psycopg2, which this project does not install, and the
    deploy dies at start-up with a driver error that says nothing about what is wrong.

    Exported rather than kept private because alembic/env.py needs it too, and env.py has
    to call it on the URL it reads at that moment: the migration tests point Alembic at a
    throwaway database by swapping the environment variable around the call. Handing it
    this module's DATABASE_URL instead would freeze the value at import time and quietly
    migrate the wrong database - which is exactly what happened when it was tried.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url  # already names a driver, or is not PostgreSQL at all


DATABASE_URL = with_driver(os.environ["DATABASE_URL"])

# Origins whose pages may call this API from a browser: scheme + host + port, no path.
# A comma-separated list, e.g. "https://shop.example.com,http://localhost:5173".
# The default is the Vite dev server, so running locally needs no configuration.
CORS_ORIGINS = [
    origin.strip().rstrip("/")  # a browser never sends a trailing slash, so it would never match
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

# Folder with the product images; the API serves it as static files under /images.
# parents[2] walks up from app/config.py to the root of the repository: app -> backend -> root.
# Docker mounts that same folder somewhere else and sets IMAGES_DIR to say where.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
IMAGES_DIR = Path(os.environ.get("IMAGES_DIR", REPOSITORY_ROOT / "data" / "images"))
