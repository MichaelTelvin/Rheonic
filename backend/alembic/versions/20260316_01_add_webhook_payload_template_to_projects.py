from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260316_01"
down_revision = "20260309_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("webhook_payload_template_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "webhook_payload_template_json")
