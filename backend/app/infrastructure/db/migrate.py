from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    root_dir = Path(__file__).resolve().parents[3]
    alembic_config = Config(str(root_dir / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    engine = create_engine(database_url)
    inspector = inspect(engine)
    has_alembic_version = inspector.has_table("alembic_version")
    has_existing_schema = any(
        inspector.has_table(table_name)
        for table_name in ("users", "projects", "events", "incidents", "ingest_keys")
    )

    # If schema already exists from prior bootstrap, mark it at baseline once.
    if has_existing_schema and not has_alembic_version:
        command.stamp(alembic_config, "head")

    command.upgrade(alembic_config, "head")


if __name__ == "__main__":
    main()
