import os
from pathlib import Path

from dotenv import load_dotenv

# Everything the app reads from the environment lives in this one file.
load_dotenv()  # finds .env by walking up from this file, so it works from any directory

DATABASE_URL = os.environ["DATABASE_URL"]

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

# TEMPORARY: every order is placed for this same customer, because there are no users yet.
# The next checkpoint adds registration and sign-in, and then the buyer comes from the
# session instead. Keeping it here, with a name that says what it is, means there is one
# obvious line to delete when that happens - instead of an address buried in the services.
PLACEHOLDER_CUSTOMER_EMAIL = "customer@evolve-shop.example"
