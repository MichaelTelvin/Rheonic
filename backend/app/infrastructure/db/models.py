# Database model placeholders.
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    # Base class for SQLAlchemy declarative models.
    pass


class EventRecord(Base):
    # Persistence record for events.
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_project_id_ts", "project_id", "ts"),
        Index("ix_events_ts", "ts"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_feature: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class IncidentRecord(Base):
    # Persistence record for incidents.
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_project_status_fingerprint", "project_id", "status", "fingerprint"),
        Index("ix_incidents_project_provider_status_created_at", "project_id", "provider", "status", "created_at"),
        Index("ix_incidents_project_provider_last_seen_at", "project_id", "provider", "last_seen_at"),
        Index("ix_incidents_project_status_created_at", "project_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown", server_default="unknown")
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectRecord(Base):
    # Persistence record for projects.
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_projects_user_id_name"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True, index=True)
    protect_enabled: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    protect_fail_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="open", server_default="open")
    apply_clamp: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    protect_max_req_per_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protect_max_tok_per_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protect_decision_timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")
    webhook_enabled: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    webhook_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    webhook_last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    webhook_last_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    webhook_last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ProjectModelRecord(Base):
    # Persistence record for first-seen provider/model per project.
    __tablename__ = "project_models"
    __table_args__ = (
        UniqueConstraint("project_id", "provider", "model", name="uq_project_models_project_provider_model"),
        Index("ix_project_models_project_id", "project_id"),
        Index("ix_project_models_provider", "provider"),
        Index("ix_project_models_model", "model"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class IngestKeyRecord(Base):
    # Persistence record for project ingest keys.
    __tablename__ = "ingest_keys"
    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_ingest_keys_key_hash"),
        Index("ix_ingest_keys_project_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PricingRecord:
    # Persistence record placeholder for pricing.
    pass


class UserRecord(Base):
    # Persistence record for users.
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
