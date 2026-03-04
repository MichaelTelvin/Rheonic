"""Add email_enabled to projects.

Revision ID: 20260304_01
Revises: 20260226_01
Create Date: 2026-03-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260304_01"
down_revision = "20260226_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("projects", "email_enabled")
