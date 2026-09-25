"""What the shop says about itself, and how it says it.

One rule, and everything here follows from it: THE SHOP WRITES TO STDOUT AND NOTHING ELSE.
No Elasticsearch client, no host, no credentials, no library. Something outside picks the
lines up. So if the logging stack is down, slow, full or replaced, the shop carries on
selling, which is not true of an application that posts its own logs over the network.

Two decisions worth reading before the code:

WHY JSON, WHEN JSON IS HARDER TO READ. A line like

    Order 12 failed for ana@example.com after 431ms

is pleasant for a person and nearly useless for a machine: answering "what is the 95th
percentile of order latency this week" means parsing English with a regular expression, and
the regular expression breaks the day somebody rewords the message. Written as fields, that
question is a filter and an aggregation. The cost is real - nobody enjoys reading JSON in a
terminal - and it is paid once, by the developer, instead of every time anybody asks the
logs a question.

WHY ECS FIELD NAMES. `http.response.status_code` rather than `status`. Elastic Common Schema
is Elastic's agreed vocabulary, and using it means Kibana already knows what these fields
mean: filters, dashboards and alerts work without configuring anything. Inventing names
costs nothing today and costs a mapping exercise for every tool, forever.
"""

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar

SERVICE_NAME = "shop-api"
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# The id of the request being served right now, readable from anywhere without passing it
# down through every function. A ContextVar and not a global: each request gets its own
# value even when several are in flight, which a plain module variable could not do.
#
# It is what turns a pile of lines into a story: filter by it and you have everything that
# happened while serving one person's click, in order.
current_request_id: ContextVar[str] = ContextVar("current_request_id", default="")


class EcsFormatter(logging.Formatter):
    """Turns a log record into one line of JSON using Elastic Common Schema names."""

    def format(self, record: logging.LogRecord) -> str:
        event = {
            # The name Elasticsearch expects for the time field. Not "time", not
            # "timestamp": a data stream REQUIRES @timestamp and rejects documents without
            # it. In UTC and with a Z, because a log with a local time and no offset is a
            # log you cannot compare with anybody else's.
            "@timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "log.level": record.levelname.lower(),
            "log.logger": record.name,
            "message": record.getMessage(),
            "service.name": SERVICE_NAME,
            # Which shop this is. One Elasticsearch can hold several and this is what keeps
            # a developer's experiments out of the production dashboards.
            "service.environment": ENVIRONMENT,
        }

        request_id = current_request_id.get()
        if request_id:
            event["trace.id"] = request_id

        # Anything passed as logger.info("...", extra={"http.response.status_code": 200}).
        # Reserved attributes of LogRecord are skipped so the shop cannot accidentally
        # overwrite the fields above.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                event[key] = value

        if record.exc_info:
            # The stack trace as a field rather than as extra lines, so that one failure is
            # one document. Split across lines it becomes twenty unrelated documents and
            # the one that says what broke is the hardest to find.
            event["error.stack_trace"] = self.formatException(record.exc_info)
            event["error.type"] = record.exc_info[0].__name__

        return json.dumps(event, ensure_ascii=False, default=str)


# Everything logging puts on a record by itself. Anything else came from `extra`.
_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", "taskName"}


def configure_logging() -> None:
    """Point the root logger at stdout, in JSON, once."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(EcsFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(LOG_LEVEL)

    # uvicorn installs its own handlers and its access log writes a line in its own format
    # that nothing here can parse. The middleware below produces a better one - with a
    # duration and a request id - so this silences the duplicate.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


log = logging.getLogger("shop")


async def log_requests(request, call_next):
    """One line per request, with everything needed to answer questions about it later.

    Deliberately NOT a decorator on each route: a middleware sees every request, including
    the ones that fail before reaching any code of ours - a 404, a malformed body, a route
    that does not exist. Those are exactly the requests nobody remembers to instrument.
    """
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    current_request_id.set(request_id)
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        # Logged and re-raised: this middleware reports, it does not decide. Swallowing it
        # here would turn a crash into a silent 500 with no trace anywhere.
        log.exception(
            "request failed",
            extra={
                "http.request.method": request.method,
                "url.path": request.url.path,
                "event.duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    log.info(
        f"{request.method} {request.url.path} {response.status_code}",
        extra={
            "http.request.method": request.method,
            "url.path": request.url.path,
            "http.response.status_code": response.status_code,
            "event.duration_ms": duration_ms,
        },
    )
    # Handed back so that a person reporting a problem can quote the id of the request that
    # failed, instead of "it broke around four o'clock".
    response.headers["X-Request-Id"] = request_id
    return response
