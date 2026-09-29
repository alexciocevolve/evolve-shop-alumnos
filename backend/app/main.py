from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import CORS_ORIGINS, IMAGES_DIR
from app.observability import configure_logging, log, log_requests
from app.routes import cart, categories, orders, products, users

# Before anything else builds a logger of its own. Calling it later would leave whatever
# logged during import writing in a different format, and those are the lines that explain
# a start-up that failed.
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # What runs before `yield` happens once at start-up, and what runs after it happens
    # once when the server stops. (FastAPI used to do this with @app.on_event("startup"),
    # which is deprecated now.)
    #
    # Not decoration: it is the line that proves the whole chain works. If this turns up in
    # Kibana, the shop is writing JSON, Filebeat is reading it and Elasticsearch is
    # storing it - three things confirmed by one message.
    log.info("shop started", extra={"event.action": "startup"})
    yield
    # A clean stop leaves this line. Two "shop started" in a row with no "shop stopped"
    # in between mean the first one did not stop: it crashed or was killed.
    log.info("shop stopped", extra={"event.action": "shutdown"})


app = FastAPI(title="Shop API", lifespan=lifespan)

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

# One line per request, with its method, path, status, duration and id.
app.middleware("http")(log_requests)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(cart.router)
app.include_router(categories.router)
app.include_router(orders.router)
app.include_router(products.router)
app.include_router(users.router)

# Static files: GET /images/product-1.svg returns that file from IMAGES_DIR. No route
# function, no database: the server just reads the file and sends it (with ETag and
# Last-Modified, so browsers can ask "has it changed?" and get a cheap 304).
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")
