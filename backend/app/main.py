from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.config import CORS_ORIGINS, IMAGES_DIR
from app.db import engine
from app.observability import configure_logging, log, log_requests
from app.routes import cart, categories, orders, products, users

# Before anything else builds a logger of its own. Calling it later would leave whatever
# logged during import writing in a different format, and those are the lines that explain
# a start-up that failed.
configure_logging()

# How long start-up waits for the database before saying it is unreachable. An address that
# nothing answers does not always reply "no": on some networks the attempt just hangs for
# about two minutes, and until this check returns, the shop does not serve anybody.
STARTUP_CHECK_TIMEOUT_SECONDS = 5


def say_whether_the_database_answers() -> None:
    # Once, at start-up: where the database is and whether it answers.
    #
    # The region mistake in render.yaml was a shop that started without complaint and then
    # could not reach its database, so every request failed and /health still said "ok"
    # (it does not touch the database). This line puts the answer at the top of the logs.
    #
    # It reports and nothing more. The shop keeps starting either way, because a database
    # that is still waking up is not a reason to refuse to run.
    #
    # engine.url.host and .database, never the whole URL: the URL has the password in it.
    where = {"destination.address": engine.url.host, "shop.database": engine.url.database}
    # A throwaway engine for this one question, so that the time limit applies here only
    # and not to every connection the shop opens afterwards.
    probe = create_engine(
        engine.url,
        connect_args={"connect_timeout": STARTUP_CHECK_TIMEOUT_SECONDS},
        poolclass=NullPool,
    )
    try:
        with probe.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001 - any failure here means the same thing
        probe.dispose()
        log.error(
            "database unreachable",
            extra={
                "event.action": "startup.database",
                "event.outcome": "failure",
                "error.message": str(e),
                **where,
            },
        )
        return
    probe.dispose()
    log.info(
        "database reachable",
        extra={"event.action": "startup.database", "event.outcome": "success", **where},
    )


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
    say_whether_the_database_answers()
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
