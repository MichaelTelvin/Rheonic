"""drop project protect timeout column

Revision ID: 20260309_01
Revises: 20260305_01
Create Date: 2026-03-09
"""

from alembic import op
import sqlalchemy as sa


revision = "20260309_01"
down_revision = "20260305_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("projects")}
    if "protect_decision_timeout_ms" in columns:
        op.drop_column("projects", "protect_decision_timeout_ms")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("projects")}
    if "protect_decision_timeout_ms" not in columns:
        op.add_column(
            "projects",
            sa.Column("protect_decision_timeout_ms", sa.Integer(), server_default="250", nullable=False),
        )
