from datetime import datetime, timezone

from app.application.services.transport_service import TransportService, build_transport_dedupe_key
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base, TransportOutboxRecord
from app.infrastructure.db.repositories.transport_outbox_repository_impl import TransportOutboxRepositoryImpl
from app.logger import bind_trace_context, reset_trace_context


def test_transport_service_dedupe_key_prevents_duplicates(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_service_dedupe.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    enqueued: list[str] = []
    service = TransportService(
        outbox_repository=TransportOutboxRepositoryImpl(session_factory=session_factory),
        enqueue_job=lambda outbox_id: enqueued.append(outbox_id),
        now_provider=lambda: datetime.now(timezone.utc),
    )

    first = service.enqueue(
        project_id="p1",
        kind="webhook",
        event_type="incident.warn",
        payload={"body": {"event": "incident.warn"}},
        dedupe_key="dedupe-1",
    )
    second = service.enqueue(
        project_id="p1",
        kind="webhook",
        event_type="incident.warn",
        payload={"body": {"event": "incident.warn"}},
        dedupe_key="dedupe-1",
    )

    assert first == second
    assert enqueued == [first]

    with session_factory.create_session() as session:
        assert session.query(TransportOutboxRecord).count() == 1


def test_transport_service_enqueue_writes_expected_outbox_fields(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_service_fields.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    service = TransportService(
        outbox_repository=TransportOutboxRepositoryImpl(session_factory=session_factory),
        enqueue_job=lambda outbox_id: None,
        now_provider=lambda: datetime.now(timezone.utc),
    )

    outbox_id = service.enqueue(
        project_id="p2",
        kind="email",
        event_type="feedback.submitted",
        payload={"message": "hello"},
        dedupe_key="email-dedupe-1",
        destination="ops@example.com",
        subject="Subject",
        template="feedback_submitted",
        severity="low",
        provider="openai",
        environment="prod",
    )

    with session_factory.create_session() as session:
        row = session.query(TransportOutboxRecord).filter(TransportOutboxRecord.id == outbox_id).first()
        assert row is not None
        assert row.project_id == "p2"
        assert row.kind == "email"
        assert row.event_type == "feedback.submitted"
        assert row.destination == "ops@example.com"
        assert row.subject == "Subject"
        assert row.template == "feedback_submitted"
        assert row.status == "pending"
        assert row.attempts == 0
        assert row.max_attempts == 1
        assert row.payload["message"] == "hello"
        assert row.payload["severity"] == "low"
        assert row.payload["provider"] == "openai"
        assert row.payload["environment"] == "prod"


def test_build_transport_dedupe_key_is_stable_for_same_payload_semantics() -> None:
    first = build_transport_dedupe_key(
        project_id="p1",
        kind="email",
        event_type="feedback.submitted",
        payload={"b": 2, "a": 1},
        destination="ops@example.com",
        seed="u1",
    )
    second = build_transport_dedupe_key(
        project_id="p1",
        kind="email",
        event_type="feedback.submitted",
        payload={"a": 1, "b": 2},
        destination="ops@example.com",
        seed="u1",
    )
    different = build_transport_dedupe_key(
        project_id="p1",
        kind="email",
        event_type="feedback.submitted",
        payload={"a": 1, "b": 2},
        destination="ops@example.com",
        seed="u2",
    )
    assert first == second
    assert first != different


def test_transport_service_origin_trace_id_uses_bound_context_not_worker_trace_override(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_service_origin_trace.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    service = TransportService(
        outbox_repository=TransportOutboxRepositoryImpl(session_factory=session_factory),
        enqueue_job=lambda outbox_id, **kwargs: None,
        now_provider=lambda: datetime.now(timezone.utc),
    )

    tokens = bind_trace_context(trace_id="backend-trace-123")
    try:
        outbox_id = service.enqueue(
            project_id="p3",
            kind="webhook",
            event_type="incident.warn",
            payload={"body": {"event": "incident.warn"}},
            dedupe_key="origin-trace-dedupe-1",
            trace_id="worker-trace-999",
        )
    finally:
        reset_trace_context(tokens)

    with session_factory.create_session() as session:
        row = session.query(TransportOutboxRecord).filter(TransportOutboxRecord.id == outbox_id).first()
        assert row is not None
        transport_meta = row.payload.get("__transport_meta")
        assert isinstance(transport_meta, dict)
        assert transport_meta.get("origin_trace_id") == "backend-trace-123"
