from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import Settings


def main() -> None:
    database_url = Settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    root_dir = Path(__file__).resolve().parents[3]
    alembic_config = Config(str(root_dir / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_config, "head")


if __name__ == "__main__":
    main()
