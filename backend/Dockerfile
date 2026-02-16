FROM python:3.12-slim

WORKDIR /app

# Minimal OS deps (kept small)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install runtime deps explicitly so uvicorn/rq exist in the image
# (Even if your pyproject is incomplete right now, the container will run.)
RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    rq \
    redis \
    "psycopg[binary]" \
    pydantic-settings \
    sqlalchemy

# Copy project (useful for non-mounted runs; in dev you'll mount via compose)
COPY . .

EXPOSE 8000