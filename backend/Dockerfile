FROM python:3.12-slim

WORKDIR /app
ARG INSTALL_DEV=false

# Keep image slim while allowing package builds when needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install backend dependencies from pyproject for reproducible builds.
COPY pyproject.toml ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN pip install --no-cache-dir -U pip \
    && if [ "$INSTALL_DEV" = "true" ]; then pip install --no-cache-dir ".[dev]"; else pip install --no-cache-dir .; fi

EXPOSE 8000
