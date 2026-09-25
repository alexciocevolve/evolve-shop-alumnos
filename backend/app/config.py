import os

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
