from __future__ import annotations

from sqlalchemy import text

from app.dependencies import get_db_session_factory, get_redis_client


def assert_critical_dependencies_ready() -> None:
    with get_db_session_factory().create_session() as session:
        session.execute(text("SELECT 1"))
    if not get_redis_client().ping():
        raise RuntimeError("redis ping failed")
