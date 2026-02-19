# Test safety guardrails to prevent accidental dev data mutation.
from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest


@pytest.fixture(scope="session", autouse=True)
def enforce_test_isolation_contract() -> None:
    app_env = os.getenv("APP_ENV", "")
    database_url = os.getenv("DATABASE_URL", "")
    redis_url = os.getenv("REDIS_URL", "")

    if app_env != "test":
        raise RuntimeError(
            "Backend tests require APP_ENV=test. Refusing to run outside test isolation."
        )

    if not database_url:
        raise RuntimeError("Backend tests require DATABASE_URL to be set.")
    if not redis_url:
        raise RuntimeError("Backend tests require REDIS_URL to be set.")

    db = urlparse(database_url)
    db_name = db.path.lstrip("/").split("?")[0]
    db_host = db.hostname or ""

    if not db_name.startswith("llmtbg_test"):
        raise RuntimeError(
            f"Unsafe DATABASE_URL for tests: expected test DB name starting with 'llmtbg_test', got '{db_name}'."
        )
    if db_name == "llmtbg":
        raise RuntimeError("Unsafe DATABASE_URL for tests: dev database 'llmtbg' is not allowed.")
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
