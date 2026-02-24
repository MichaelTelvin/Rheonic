"""scope incidents by provider

Revision ID: 20260224_02
Revises: 20260224_01
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260224_02"
down_revision = "20260224_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("provider", sa.String(length=64), nullable=True))

    # Best-effort backfill from incident evidence provider when available.
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        bind.execute(
            sa.text(
                "UPDATE incidents "
                "SET provider = NULLIF(TRIM(evidence->>'provider'), '') "
                "WHERE provider IS NULL"
            )
        )
    elif dialect == "sqlite":
        bind.execute(
            sa.text(
                "UPDATE incidents "
                "SET provider = NULLIF(TRIM(json_extract(evidence, '$.provider')), '') "
                "WHERE provider IS NULL"
            )
        )

    # Remaining rows are unknown until enriched by new ingest/provider-scoped flows.
    bind.execute(sa.text("UPDATE incidents SET provider = 'unknown' WHERE provider IS NULL OR provider = ''"))

    op.alter_column("incidents", "provider", nullable=False, server_default="unknown")
    op.create_index(
        "ix_incidents_project_provider_status_created_at",
        "incidents",
        ["project_id", "provider", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_incidents_project_provider_last_seen_at",
        "incidents",
        ["project_id", "provider", "last_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_incidents_project_provider_last_seen_at", table_name="incidents")
    op.drop_index("ix_incidents_project_provider_status_created_at", table_name="incidents")
    op.drop_column("incidents", "provider")
