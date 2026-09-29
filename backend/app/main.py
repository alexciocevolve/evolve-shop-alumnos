from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import CORS_ORIGINS, IMAGES_DIR
from app.routes import products

app = FastAPI(title="Shop API")

# The browser treats the page's origin (e.g. localhost:5173, Vite) and this API's origin
# (localhost:8000) as different, so the API has to say explicitly which pages may call it.
# The list comes from the CORS_ORIGINS environment variable, so deploying the frontend
# somewhere else means changing configuration, not code.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(products.router)

# Static files: GET /images/product-1.svg returns that file from IMAGES_DIR. No route
# function, no database: the server just reads the file and sends it (with ETag and
# Last-Modified, so browsers can ask "has it changed?" and get a cheap 304).
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")
