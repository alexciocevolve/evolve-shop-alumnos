FROM python:3.12-slim

# NOTE: this image is built with the REPOSITORY ROOT as its context, not backend/, which is
# why every path below starts with backend/ or data/. The reason is three lines down: the
# product images live in data/images and have to travel inside the image.
#   docker compose build            (compose says context: .)
#   docker build -f backend/Dockerfile .

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# Dependencies first: this layer is rebuilt only when requirements.txt changes.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# The product images, INSIDE the image. On a laptop they arrive through a bind mount, which
# is how you can drop a new photograph in without rebuilding; a container in the cloud has
# no such folder, and Render's free plan has no persistent disk either. Baking them in is
# right for what they are: 2.7 MB of seed data, committed to the repository, named by the
# migrations, and never written to at run time.
#
# The day they stop being that - the day somebody uploads a photograph from a screen - this
# stops being right and they belong in object storage (S3, R2) with the address in the
# database. Which is the same conversation as any other file an application accepts.
COPY data/images /app/images
ENV IMAGES_DIR=/app/images


EXPOSE 8000

# ${PORT:-8000}: a host like Render picks the port and passes it in, and a server that
# listens anywhere else is a service that never answers. 8000 stays as the default so
# docker compose and a plain `docker run` behave exactly as before.
#
# The migration still runs here, and it is still a convenience rather than a practice: with
# more than one instance they would all migrate at once. In production it is a separate
# deployment step - render.yaml uses preDeployCommand and replaces this whole command.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
