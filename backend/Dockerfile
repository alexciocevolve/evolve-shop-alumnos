# The API in a container.
#
# At this checkpoint only the database was in Docker and the backend was started by hand.
# Two things changed that, and only one of them is about teaching:
#
#   · A log collector reads what a CONTAINER writes to stdout. With the API running loose
#     on somebody's laptop there is nothing to read, and the whole point of this branch is
#     that the logs end up somewhere they can be searched.
#   · And on this machine the API cannot run outside a container at all: Windows
#     Application Control blocks the unsigned libpq DLL that psycopg ships, so every
#     import of it dies before the first line of the shop runs.
#
# Layers are ordered by how often they change, which is what decides whether a rebuild
# takes three seconds or three minutes.

FROM python:3.12-slim

WORKDIR /app

# Dependencies first: this layer is rebuilt only when requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# And the code last, because it changes on every commit.
COPY . .

EXPOSE 8000

# Migrations run before the server accepts traffic. It is a convenience and not a
# practice: with more than one instance they would all migrate at once, and the right
# place is a release phase that runs once. With one instance it is also the only option.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
