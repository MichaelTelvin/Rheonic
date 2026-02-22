"""add project webhook columns

Revision ID: 20260222_01
Revises:
Create Date: 2026-02-22
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260222_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("webhook_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("projects", sa.Column("webhook_url", sa.String(length=2048), nullable=True))
    op.add_column("projects", sa.Column("webhook_secret", sa.String(length=512), nullable=True))
    op.add_column("projects", sa.Column("webhook_last_status", sa.String(length=16), nullable=True))
    op.add_column("projects", sa.Column("webhook_last_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("projects", sa.Column("webhook_last_error", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "webhook_last_error")
    op.drop_column("projects", "webhook_last_at")
    op.drop_column("projects", "webhook_last_status")
    op.drop_column("projects", "webhook_secret")
    op.drop_column("projects", "webhook_url")
    op.drop_column("projects", "webhook_enabled")
