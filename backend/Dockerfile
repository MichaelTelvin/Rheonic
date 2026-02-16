FROM python:3.12-slim

WORKDIR /app

# Keep image slim while allowing package builds when needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install backend dependencies from pyproject for reproducible builds.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir ".[dev]"

EXPOSE 8000
