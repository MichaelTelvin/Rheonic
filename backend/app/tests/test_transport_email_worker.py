import json
from datetime import datetime, timezone

from app.application.services.transport_service import TransportService
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base, ProjectRecord, TransportOutboxRecord, UserRecord
from app.infrastructure.db.repositories.transport_outbox_repository_impl import TransportOutboxRepositoryImpl
from app.infrastructure.jobs import transport_job


class _FakeQueue:
    def enqueue_in(self, delay, func, kwargs):
        _ = delay, func, kwargs
        return None


class _FakeEmailResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {"id": "email_123"}


class _FakeEmailClient:
    def __init__(self, sent: list[dict[str, object]]) -> None:
        self.sent = sent

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb

    def post(self, url: str, json: dict[str, object], headers: dict[str, str]):
        self.sent.append({"url": url, "json": json, "headers": headers})
        return _FakeEmailResponse()


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


def test_feedback_email_delivery_uses_system_sender_and_reply_to(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_email_feedback_delivery.db"
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
        payload={"report_type": "bug", "message": "test", "timestamp": "2026-03-15T10:00:00Z"},
        dedupe_key="feedback-email-delivery",
        template="feedback_submitted",
    )

    sent: list[dict[str, object]] = []
    settings = transport_job.Settings(
        database_url=db_url,
        redis_url="redis://localhost:6379/15",
        resend_api_key="re_test",
        email_from_alerts="Rheonic Alerts <alerts@mail.rheonic.dev>",
        email_from_system="Rheonic System <system@mail.rheonic.dev>",
        email_reply_to="contact@rheonic.dev",
        feedback_report_email="ops@rheonic.dev",
    )
    monkeypatch.setattr(transport_job, "Settings", lambda: settings)
    monkeypatch.setattr(transport_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    monkeypatch.setattr(transport_job.httpx, "Client", lambda timeout: _FakeEmailClient(sent))
    monkeypatch.setattr(transport_job, "Queue", lambda *args, **kwargs: _FakeQueue())

    transport_job.process_outbox_delivery(outbox_id)

    assert len(sent) == 1
    payload = sent[0]["json"]
    assert sent[0]["url"] == "https://api.resend.com/emails"
    assert payload["from"] == "Rheonic System <system@mail.rheonic.dev>"
    assert payload["to"] == ["ops@rheonic.dev"]
    assert payload["reply_to"] == ["contact@rheonic.dev"]
    assert payload["subject"] == "Rheonic beta bug report"
    assert payload["attachments"][0]["filename"] == "rheonic-logo.png"
    assert payload["attachments"][0]["content_type"] == "image/png"
    assert payload["attachments"][0]["content_id"] == "rheonic-logo"


def test_feedback_email_delivery_passes_screenshot_attachment_to_provider(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_email_feedback_attachment.db"
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
        payload={
            "report_type": "bug",
            "message": "test",
            "timestamp": "2026-03-15T10:00:00Z",
            "screenshot_name": "bug.png",
            "screenshot_content_type": "image/png",
            "screenshot_base64": "ZmFrZS1wbmctYnl0ZXM=",
        },
        dedupe_key="feedback-email-attachment",
        template="feedback_submitted",
    )

    sent: list[dict[str, object]] = []
    settings = transport_job.Settings(
        database_url=db_url,
        redis_url="redis://localhost:6379/15",
        resend_api_key="re_test",
        email_from_alerts="Rheonic Alerts <alerts@mail.rheonic.dev>",
        email_from_system="Rheonic System <system@mail.rheonic.dev>",
        email_reply_to="contact@rheonic.dev",
        feedback_report_email="ops@rheonic.dev",
    )
    monkeypatch.setattr(transport_job, "Settings", lambda: settings)
    monkeypatch.setattr(transport_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    monkeypatch.setattr(transport_job.httpx, "Client", lambda timeout: _FakeEmailClient(sent))
    monkeypatch.setattr(transport_job, "Queue", lambda *args, **kwargs: _FakeQueue())

    transport_job.process_outbox_delivery(outbox_id)

    assert len(sent) == 1
    attachments = sent[0]["json"]["attachments"]
    assert attachments[0]["filename"] == "rheonic-logo.png"
    assert attachments[0]["content_type"] == "image/png"
    assert attachments[0]["content_id"] == "rheonic-logo"
    assert attachments[1:] == [
        {
            "filename": "bug.png",
            "content": "ZmFrZS1wbmctYnl0ZXM=",
            "content_type": "image/png",
        }
    ]


def test_alert_email_delivery_resolves_project_owner_and_alert_sender(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_email_alert_delivery.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    now = datetime.now(timezone.utc)
    with session_factory.create_session() as session:
        session.add(UserRecord(id="u1", email="owner@example.com", password_hash="hashed", created_at=now))
        session.add(
            ProjectRecord(
                id="p-alert",
                name="Alert",
                user_id="u1",
                protect_enabled=True,
                protect_fail_mode="open",
                email_enabled=True,
                created_at=now,
            )
        )
        session.commit()

    service = TransportService(
        outbox_repository=TransportOutboxRepositoryImpl(session_factory=session_factory),
        enqueue_job=lambda outbox_id: None,
        now_provider=lambda: datetime.now(timezone.utc),
    )
    outbox_id = service.enqueue(
        project_id="p-alert",
        kind="email",
        event_type="protection.block",
        payload={
            "project_id": "p-alert",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "environment": "prod",
            "reason": "cap_breach",
            "detail_reason": "req_cap_breach",
            "blocked_until": "2026-03-15T10:01:00Z",
            "retry_after_seconds": 60,
            "source": "live",
            "sent_at": "2026-03-15T10:00:00Z",
        },
        dedupe_key="incident-block-email-delivery",
        template="protection_block",
    )

    sent: list[dict[str, object]] = []
    settings = transport_job.Settings(
        database_url=db_url,
        redis_url="redis://localhost:6379/15",
        resend_api_key="re_test",
        email_from_alerts="Rheonic Alerts <alerts@mail.rheonic.dev>",
        email_from_system="Rheonic System <system@mail.rheonic.dev>",
        email_reply_to="contact@rheonic.dev",
    )
    monkeypatch.setattr(transport_job, "Settings", lambda: settings)
    monkeypatch.setattr(transport_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    monkeypatch.setattr(transport_job.httpx, "Client", lambda timeout: _FakeEmailClient(sent))
    monkeypatch.setattr(transport_job, "Queue", lambda *args, **kwargs: _FakeQueue())

    transport_job.process_outbox_delivery(outbox_id)

    assert len(sent) == 1
    payload = sent[0]["json"]
    assert payload["from"] == "Rheonic Alerts <alerts@mail.rheonic.dev>"
    assert payload["to"] == ["owner@example.com"]
    assert payload["reply_to"] == ["contact@rheonic.dev"]
    assert payload["subject"] == "[Rheonic] Protect alert: Request cap exceeded (p-alert)"
    assert payload["attachments"][0]["filename"] == "rheonic-logo.png"
    assert payload["attachments"][0]["content_id"] == "rheonic-logo"


def test_alert_email_delivery_is_skipped_when_project_email_alerts_are_disabled(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_email_alert_skipped.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    now = datetime.now(timezone.utc)
    with session_factory.create_session() as session:
        session.add(UserRecord(id="u1", email="owner@example.com", password_hash="hashed", created_at=now))
        session.add(
            ProjectRecord(
                id="p-skip",
                name="Skip",
                user_id="u1",
                protect_enabled=True,
                protect_fail_mode="open",
                email_enabled=False,
                created_at=now,
            )
        )
        session.commit()

    service = TransportService(
        outbox_repository=TransportOutboxRepositoryImpl(session_factory=session_factory),
        enqueue_job=lambda outbox_id: None,
        now_provider=lambda: datetime.now(timezone.utc),
    )
    outbox_id = service.enqueue(
        project_id="p-skip",
        kind="email",
        event_type="protection.warn",
        payload={
            "project_id": "p-skip",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "environment": "prod",
            "reason": "retry_storm",
            "requests_60s": 12,
            "tokens_60s": 600,
            "req_cap": 400,
            "tok_cap": 1700,
            "estimated_next_tokens": 60,
            "sent_at": "2026-03-15T10:00:00Z",
        },
        dedupe_key="incident-warn-email-skipped",
        template="protection_warn",
    )

    sent: list[dict[str, object]] = []
    settings = transport_job.Settings(
        database_url=db_url,
        redis_url="redis://localhost:6379/15",
        resend_api_key="re_test",
        email_from_alerts="Rheonic Alerts <alerts@mail.rheonic.dev>",
        email_from_system="Rheonic System <system@mail.rheonic.dev>",
        email_reply_to="contact@rheonic.dev",
    )
    monkeypatch.setattr(transport_job, "Settings", lambda: settings)
    monkeypatch.setattr(transport_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    monkeypatch.setattr(transport_job.httpx, "Client", lambda timeout: _FakeEmailClient(sent))
    monkeypatch.setattr(transport_job, "Queue", lambda *args, **kwargs: _FakeQueue())

    transport_job.process_outbox_delivery(outbox_id)

    assert sent == []
    with session_factory.create_session() as session:
        row = session.query(TransportOutboxRecord).filter(TransportOutboxRecord.id == outbox_id).first()
        assert row is not None
        assert row.status == "delivered"


def test_alert_email_skip_logs_outbox_skipped_instead_of_outbox_delivered(
    tmp_path, monkeypatch, capsys
) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_email_alert_skip_logs.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    now = datetime.now(timezone.utc)
    with session_factory.create_session() as session:
        session.add(UserRecord(id="u1", email="owner@example.com", password_hash="hashed", created_at=now))
        session.add(
            ProjectRecord(
                id="p-skip-log",
                name="SkipLog",
                user_id="u1",
                protect_enabled=True,
                protect_fail_mode="open",
                email_enabled=False,
                created_at=now,
            )
        )
        session.commit()

    service = TransportService(
        outbox_repository=TransportOutboxRepositoryImpl(session_factory=session_factory),
        enqueue_job=lambda outbox_id: None,
        now_provider=lambda: datetime.now(timezone.utc),
    )
    outbox_id = service.enqueue(
        project_id="p-skip-log",
        kind="email",
        event_type="incident.resolved",
        payload={
            "project_id": "p-skip-log",
            "incident_id": "i-1",
            "incident_type": "retry_storm",
            "resolved_by": "manual",
            "resolved_at": "2026-03-19T11:00:00Z",
            "created_at": "2026-03-19T10:55:00Z",
            "last_seen_at": "2026-03-19T10:59:00Z",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "environment": "staging",
            "sent_at": "2026-03-19T11:00:00Z",
        },
        dedupe_key="incident-resolved-email-skipped-log",
        template="incident_resolved",
    )

    sent: list[dict[str, object]] = []
    settings = transport_job.Settings(
        database_url=db_url,
        redis_url="redis://localhost:6379/15",
        resend_api_key="re_test",
        email_from_alerts="Rheonic Alerts <alerts@mail.rheonic.dev>",
        email_from_system="Rheonic System <system@mail.rheonic.dev>",
        email_reply_to="contact@rheonic.dev",
    )
    monkeypatch.setattr(transport_job, "Settings", lambda: settings)
    monkeypatch.setattr(transport_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    monkeypatch.setattr(transport_job.httpx, "Client", lambda timeout: _FakeEmailClient(sent))
    monkeypatch.setattr(transport_job, "Queue", lambda *args, **kwargs: _FakeQueue())

    transport_job.process_outbox_delivery(outbox_id, trace_id="trace-email-skip", span_id="span-email-skip")

    emitted = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    assert any(payload.get("event") == "email_skipped" for payload in emitted)
    skipped_log = next(payload for payload in emitted if payload.get("event") == "outbox_skipped")
    assert skipped_log["metadata"]["skip_reason"] == "email_disabled_or_missing_project"
    assert not any(payload.get("event") == "outbox_delivered" for payload in emitted)
