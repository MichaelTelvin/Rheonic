from datetime import datetime, timezone

from app.application.services.transport_service import TransportService
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base, TransportOutboxRecord
from app.infrastructure.db.repositories.transport_outbox_repository_impl import TransportOutboxRepositoryImpl
from app.infrastructure.jobs import transport_job


class _FakeQueue:
    def enqueue_in(self, delay, func, kwargs):
        _ = delay, func, kwargs
        return None


def test_email_outbox_delivery_marks_failed_when_provider_not_configured(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_email_worker.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    service = TransportService(
        outbox_repository=TransportOutboxRepositoryImpl(session_factory=session_factory),
        enqueue_job=lambda outbox_id: None,
        now_provider=lambda: datetime.now(timezone.utc),
    )
    outbox_id = service.enqueue(
        project_id="p1",
        kind="email",
        event_type="feedback.submitted",
        payload={"message": "test"},
        dedupe_key="email-worker-dedupe",
        destination="ops@example.com",
        template="feedback_submitted",
    )

    settings = transport_job.Settings(database_url=db_url, redis_url="redis://localhost:6379/15", email_provider_enabled=False)
    monkeypatch.setattr(transport_job, "Settings", lambda: settings)
    monkeypatch.setattr(transport_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    monkeypatch.setattr(transport_job, "Queue", lambda *args, **kwargs: _FakeQueue())

    transport_job.process_outbox_delivery(outbox_id)

    with session_factory.create_session() as session:
        row = session.query(TransportOutboxRecord).filter(TransportOutboxRecord.id == outbox_id).first()
        assert row is not None
        assert row.status == "dead"
        assert row.attempts == 1
        assert row.last_error_code == "email_provider_not_configured"
