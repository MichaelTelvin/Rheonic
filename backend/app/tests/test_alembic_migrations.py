from __future__ import annotations

import os
import subprocess
import uuid

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.config import Settings


def test_alembic_upgrade_head_creates_current_schema_on_fresh_database() -> None:
    settings = Settings()
    base_url = make_url(settings.database_url)
    db_name = f"rheonic_test_alembic_{uuid.uuid4().hex[:8]}"
    admin_url = base_url.set(database="postgres")
    target_url = base_url.set(database=db_name).render_as_string(hide_password=False)

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{db_name}"'))

    try:
        subprocess.run(
            [
                "alembic",
                "-c",
                "alembic.ini",
                "upgrade",
                "head",
            ],
            check=True,
            env={**os.environ, "DATABASE_URL": target_url},
        )

        target_engine = create_engine(target_url)
        try:
            inspector = inspect(target_engine)
            table_names = set(inspector.get_table_names())
            assert {
                "users",
                "projects",
                "events",
                "incidents",
                "project_models",
                "ingest_keys",
                "transport_outbox",
                "alembic_version",
            }.issubset(table_names)

            project_columns = {column["name"] for column in inspector.get_columns("projects")}
            incident_columns = {column["name"] for column in inspector.get_columns("incidents")}
            event_columns = {column["name"] for column in inspector.get_columns("events")}
            assert "apply_clamp" in project_columns
            assert "provider" in incident_columns
            assert "token_explosion_tokens" in event_columns
        finally:
            target_engine.dispose()
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :db_name"),
                {"db_name": db_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
