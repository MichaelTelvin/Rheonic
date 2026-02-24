"""add project models table

Revision ID: 20260224_01
Revises: 20260222_01
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260224_01"
down_revision = "20260222_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_models",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "provider", "model", name="uq_project_models_project_provider_model"),
    )
    op.create_index("ix_project_models_project_id", "project_models", ["project_id"], unique=False)
    op.create_index("ix_project_models_provider", "project_models", ["provider"], unique=False)
    op.create_index("ix_project_models_model", "project_models", ["model"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_project_models_model", table_name="project_models")
    op.drop_index("ix_project_models_provider", table_name="project_models")
    op.drop_index("ix_project_models_project_id", table_name="project_models")
    op.drop_table("project_models")
