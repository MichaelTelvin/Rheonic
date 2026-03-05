"""Add transport_outbox table.

Revision ID: 20260305_01
Revises: 20260304_01
Create Date: 2026-03-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260305_01"
down_revision = "20260304_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transport_outbox",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("destination", sa.String(length=2048), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("template", sa.String(length=128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "kind", "dedupe_key", name="uq_transport_outbox_project_kind_dedupe"),
    )
    op.create_index("ix_transport_outbox_project_id", "transport_outbox", ["project_id"], unique=False)
    op.create_index(
        "ix_transport_outbox_project_kind_status",
        "transport_outbox",
        ["project_id", "kind", "status"],
        unique=False,
    )
    op.create_index(
        "ix_transport_outbox_status_next_attempt_at",
        "transport_outbox",
        ["status", "next_attempt_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transport_outbox_status_next_attempt_at", table_name="transport_outbox")
    op.drop_index("ix_transport_outbox_project_kind_status", table_name="transport_outbox")
    op.drop_index("ix_transport_outbox_project_id", table_name="transport_outbox")
    op.drop_table("transport_outbox")
