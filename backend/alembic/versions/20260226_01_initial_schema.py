"""initial schema snapshot from current ORM

Revision ID: 20260226_01
Revises: None
Create Date: 2026-02-26
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260226_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("protect_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("protect_fail_mode", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("protect_max_req_per_min", sa.Integer(), nullable=True),
        sa.Column("protect_max_tok_per_min", sa.Integer(), nullable=True),
        sa.Column("protect_decision_timeout_ms", sa.Integer(), server_default="100", nullable=False),
        sa.Column("webhook_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("webhook_url", sa.String(length=2048), nullable=True),
        sa.Column("webhook_secret", sa.String(length=512), nullable=True),
        sa.Column("webhook_last_status", sa.String(length=16), nullable=True),
        sa.Column("webhook_last_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("webhook_last_error", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_projects_user_id_name"),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"], unique=False)

    op.create_table(
        "events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("environment", sa.String(length=32), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("request_endpoint", sa.String(length=255), nullable=True),
        sa.Column("request_feature", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_project_id_ts", "events", ["project_id", "ts"], unique=False)
    op.create_index("ix_events_ts", "events", ["ts"], unique=False)

    op.create_table(
        "incidents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), server_default="unknown", nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("fingerprint", sa.String(length=255), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_project_id", "incidents", ["project_id"], unique=False)
    op.create_index("ix_incidents_status", "incidents", ["status"], unique=False)
    op.create_index("ix_incidents_fingerprint", "incidents", ["fingerprint"], unique=False)
    op.create_index(
        "ix_incidents_project_status_fingerprint",
        "incidents",
        ["project_id", "status", "fingerprint"],
        unique=False,
    )
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
    op.create_index(
        "ix_incidents_project_status_created_at",
        "incidents",
        ["project_id", "status", "created_at"],
        unique=False,
    )

    op.create_table(
        "project_models",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "provider", "model", name="uq_project_models_project_provider_model"),
    )
    op.create_index("ix_project_models_project_id", "project_models", ["project_id"], unique=False)
    op.create_index("ix_project_models_provider", "project_models", ["provider"], unique=False)
    op.create_index("ix_project_models_model", "project_models", ["model"], unique=False)

    op.create_table(
        "ingest_keys",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("last4", sa.String(length=4), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uq_ingest_keys_key_hash"),
    )
    op.create_index("ix_ingest_keys_project_id", "ingest_keys", ["project_id"], unique=False)
    op.create_index("ix_ingest_keys_key_hash", "ingest_keys", ["key_hash"], unique=True)
    op.create_index("ix_ingest_keys_status", "ingest_keys", ["status"], unique=False)
    op.create_index("ix_ingest_keys_project_status", "ingest_keys", ["project_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ingest_keys_project_status", table_name="ingest_keys")
    op.drop_index("ix_ingest_keys_status", table_name="ingest_keys")
    op.drop_index("ix_ingest_keys_key_hash", table_name="ingest_keys")
    op.drop_index("ix_ingest_keys_project_id", table_name="ingest_keys")
    op.drop_table("ingest_keys")

    op.drop_index("ix_project_models_model", table_name="project_models")
    op.drop_index("ix_project_models_provider", table_name="project_models")
    op.drop_index("ix_project_models_project_id", table_name="project_models")
    op.drop_table("project_models")

    op.drop_index("ix_incidents_project_status_created_at", table_name="incidents")
    op.drop_index("ix_incidents_project_provider_last_seen_at", table_name="incidents")
    op.drop_index("ix_incidents_project_provider_status_created_at", table_name="incidents")
    op.drop_index("ix_incidents_project_status_fingerprint", table_name="incidents")
    op.drop_index("ix_incidents_fingerprint", table_name="incidents")
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_index("ix_incidents_project_id", table_name="incidents")
    op.drop_table("incidents")

    op.drop_index("ix_events_ts", table_name="events")
    op.drop_index("ix_events_project_id_ts", table_name="events")
    op.drop_table("events")

    op.drop_index("ix_projects_user_id", table_name="projects")
    op.drop_table("projects")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
