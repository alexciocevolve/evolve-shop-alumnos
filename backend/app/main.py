from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app.observability import configure_logging, log, log_requests
from app.routes import products

# Before anything else builds a logger of its own. Calling it later would leave whatever
# logged during import writing in a different format, and those are the lines that explain
# a start-up that failed.
configure_logging()

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

# One line per request, with its method, path, status, duration and id.
app.middleware("http")(log_requests)


@app.on_event("startup")
def say_hello():
    # Not decoration: it is the line that proves the whole chain works. If this turns up in
    # Kibana, the shop is writing JSON, Filebeat is reading it and Elasticsearch is
    # storing it - three things confirmed by one message.
    log.info("shop started", extra={"event.action": "startup"})


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(products.router)
