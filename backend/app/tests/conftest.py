# Test safety guardrails to prevent accidental dev data mutation.
from __future__ import annotations

from urllib.parse import urlparse

import pytest

from app.config import Settings


@pytest.fixture(scope="session", autouse=True)
def enforce_test_isolation_contract() -> None:
    settings = Settings()
    app_env = settings.app_env
    database_url = settings.database_url
    redis_url = settings.redis_url

    if app_env != "test":
        raise RuntimeError(
            "Backend tests require APP_ENV=test. Refusing to run outside test isolation."
        )

    db = urlparse(database_url)
    db_name = db.path.lstrip("/").split("?")[0]
    db_host = db.hostname or ""

    if not db_name.startswith("rheonic_test"):
        raise RuntimeError(
            f"Unsafe DATABASE_URL for tests: expected test DB name starting with 'rheonic_test', got '{db_name}'."
        )
    if db_name == "rheonic":
        raise RuntimeError("Unsafe DATABASE_URL for tests: dev database 'rheonic' is not allowed.")
    if db_host != "postgres_test":
        raise RuntimeError(
            f"Unsafe DATABASE_URL host for tests: expected 'postgres_test', got '{db_host or '(empty)'}'."
        )

    redis = urlparse(redis_url)
    redis_host = redis.hostname or ""
    if redis_host != "redis_test":
        raise RuntimeError(
            f"Unsafe REDIS_URL host for tests: expected 'redis_test', got '{redis_host or '(empty)'}'."
        )
