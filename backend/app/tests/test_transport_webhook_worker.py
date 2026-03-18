import json
from datetime import datetime, timedelta, timezone

import pytest

from app.application.services.transport_service import TransportService
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base, ProjectRecord, TransportOutboxRecord
from app.infrastructure.db.repositories.transport_outbox_repository_impl import TransportOutboxRepositoryImpl
from app.infrastructure.jobs import transport_job


class _FakeOkResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None


class _FakeErrorClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb

    def post(self, url: str, content: bytes, headers: dict[str, str]):
        request = transport_job.httpx.Request("POST", url, content=content, headers=headers)
        response = transport_job.httpx.Response(status_code=404, request=request)
        raise transport_job.httpx.HTTPStatusError("404", request=request, response=response)


class _FakeOkClient:
    def __init__(self, capture: list[dict[str, object]] | None = None) -> None:
        self.capture = capture if capture is not None else []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb

    def post(self, url: str, content: bytes, headers: dict[str, str]):
        self.capture.append({"url": url, "content": content, "headers": headers})
        return _FakeOkResponse()


class _FakeQueue:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def enqueue_in(self, delay: timedelta, func, kwargs):
        _ = func, kwargs
        self.calls.append(int(delay.total_seconds()))
        return None


def _seed_project(
    session_factory: DatabaseSessionFactory,
    project_id: str = "p1",
    *,
    protect_enabled: bool = True,
    webhook_payload_template_json: str | None = None,
) -> None:
    with session_factory.create_session() as session:
        session.add(
            ProjectRecord(
                id=project_id,
                name="P1",
                user_id="u1",
                protect_enabled=protect_enabled,
                protect_fail_mode="open",
                protect_max_req_per_min=None,
                protect_max_tok_per_min=None,
                webhook_enabled=True,
                webhook_url="https://example.test/hook",
                webhook_payload_template_json=webhook_payload_template_json,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()


def _enqueue_webhook_outbox(session_factory: DatabaseSessionFactory, project_id: str = "p1") -> str:
    service = TransportService(
        outbox_repository=TransportOutboxRepositoryImpl(session_factory=session_factory),
        enqueue_job=lambda outbox_id: None,
        now_provider=lambda: datetime.now(timezone.utc),
    )
    return service.enqueue(
        project_id=project_id,
        kind="webhook",
        event_type="incident.warn",
        payload={"body": {"event": "incident.warn", "project_id": project_id}},
        dedupe_key=f"dedupe-{project_id}-{datetime.now(timezone.utc).timestamp()}",
    )


def _set_due_now(session_factory: DatabaseSessionFactory, outbox_id: str) -> None:
    with session_factory.create_session() as session:
        row = session.query(TransportOutboxRecord).filter(TransportOutboxRecord.id == outbox_id).first()
        assert row is not None
        row.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.add(row)
        session.commit()


def test_process_outbox_delivery_webhook_success_marks_delivered(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_webhook_success.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    _seed_project(session_factory, "p1")
    outbox_id = _enqueue_webhook_outbox(session_factory, "p1")

    settings = transport_job.Settings(database_url=db_url, redis_url="redis://localhost:6379/15")
    monkeypatch.setattr(transport_job, "Settings", lambda: settings)
    monkeypatch.setattr(transport_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    monkeypatch.setattr(transport_job.httpx, "Client", lambda timeout: _FakeOkClient())
    monkeypatch.setattr(transport_job, "Queue", lambda *args, **kwargs: _FakeQueue())

    transport_job.process_outbox_delivery(outbox_id, trace_id="trace-123", span_id="span-456")

    with session_factory.create_session() as session:
        row = session.query(TransportOutboxRecord).filter(TransportOutboxRecord.id == outbox_id).first()
        assert row is not None
        assert row.status == "delivered"
        assert row.attempts == 1
        assert row.delivered_at is not None


def test_process_outbox_delivery_webhook_sends_in_observe_mode_when_webhook_is_enabled(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_webhook_observe_success.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    _seed_project(session_factory, "p-observe", protect_enabled=False)
    outbox_id = _enqueue_webhook_outbox(session_factory, "p-observe")

    captured: list[dict[str, object]] = []
    settings = transport_job.Settings(database_url=db_url, redis_url="redis://localhost:6379/15")
    monkeypatch.setattr(transport_job, "Settings", lambda: settings)
    monkeypatch.setattr(transport_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    monkeypatch.setattr(transport_job.httpx, "Client", lambda timeout: _FakeOkClient(captured))
    monkeypatch.setattr(transport_job, "Queue", lambda *args, **kwargs: _FakeQueue())

    transport_job.process_outbox_delivery(outbox_id, trace_id="trace-observe", span_id="span-observe")

    assert len(captured) == 1
    assert captured[0]["url"] == "https://example.test/hook"
    assert captured[0]["headers"]["X-Trace-ID"] == "trace-observe"
    assert captured[0]["headers"]["X-Span-ID"]

    with session_factory.create_session() as session:
        row = session.query(TransportOutboxRecord).filter(TransportOutboxRecord.id == outbox_id).first()
        assert row is not None
        assert row.status == "delivered"


def test_process_outbox_delivery_webhook_does_not_add_signature_header(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_webhook_no_signature.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    _seed_project(session_factory, "p-no-sig")
    outbox_id = _enqueue_webhook_outbox(session_factory, "p-no-sig")

    captured: list[dict[str, object]] = []
    settings = transport_job.Settings(database_url=db_url, redis_url="redis://localhost:6379/15")
    monkeypatch.setattr(transport_job, "Settings", lambda: settings)
    monkeypatch.setattr(transport_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    monkeypatch.setattr(transport_job.httpx, "Client", lambda timeout: _FakeOkClient(captured))
    monkeypatch.setattr(transport_job, "Queue", lambda *args, **kwargs: _FakeQueue())

    transport_job.process_outbox_delivery(outbox_id, trace_id="trace-no-sig", span_id="span-no-sig")

    assert len(captured) == 1
    assert "X-RHEONIC-Signature" not in captured[0]["headers"]


def test_process_outbox_delivery_ignores_stored_project_payload_template_for_live_webhooks(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_webhook_template_project_ignored.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    _seed_project(
        session_factory,
        "p1",
        webhook_payload_template_json="{\"text\":\"agent behavior anomaly detected\",\"project\":\"p1\",\"chat_id\":\"123456\"}",
    )
    service = TransportService(
        outbox_repository=TransportOutboxRepositoryImpl(session_factory=session_factory),
        enqueue_job=lambda outbox_id: None,
        now_provider=lambda: datetime.now(timezone.utc),
    )
    outbox_id = service.enqueue(
        project_id="p1",
        kind="webhook",
        event_type="incident.warn",
        payload={"body": {"event": "incident.warn", "project_id": "p1", "incident_type": "retry_storm"}},
        dedupe_key="render-project-template",
    )

    captured: list[dict[str, object]] = []
    settings = transport_job.Settings(database_url=db_url, redis_url="redis://localhost:6379/15")
    monkeypatch.setattr(transport_job, "Settings", lambda: settings)
    monkeypatch.setattr(transport_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    monkeypatch.setattr(transport_job.httpx, "Client", lambda timeout: _FakeOkClient(captured))
    monkeypatch.setattr(transport_job, "Queue", lambda *args, **kwargs: _FakeQueue())

    transport_job.process_outbox_delivery(outbox_id, trace_id="trace-template", span_id="span-template")

    assert len(captured) == 1
    rendered = json.loads(captured[0]["content"].decode("utf-8"))
    assert rendered["event"] == "incident.warn"
    assert rendered["incident_type"] == "retry_storm"
    assert rendered["project_id"] == "p1"
    assert "rheonic" not in rendered
    assert "chat_id" not in rendered
    assert "text" not in rendered


def test_process_outbox_delivery_webhook_failure_retries_then_dead_letters(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_webhook_failure.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    _seed_project(session_factory, "p2")
    outbox_id = _enqueue_webhook_outbox(session_factory, "p2")

    fake_queue = _FakeQueue()
    settings = transport_job.Settings(database_url=db_url, redis_url="redis://localhost:6379/15")
    monkeypatch.setattr(transport_job, "Settings", lambda: settings)
    monkeypatch.setattr(transport_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    monkeypatch.setattr(transport_job.httpx, "Client", lambda timeout: _FakeErrorClient())
    monkeypatch.setattr(transport_job, "Queue", lambda *args, **kwargs: fake_queue)

    transport_job.process_outbox_delivery(outbox_id)
    with session_factory.create_session() as session:
        first = session.query(TransportOutboxRecord).filter(TransportOutboxRecord.id == outbox_id).first()
        assert first is not None
        assert first.status == "failed"
        assert first.next_attempt_at is not None
        assert first.next_attempt_at > datetime.now()
    _set_due_now(session_factory, outbox_id)
    transport_job.process_outbox_delivery(outbox_id)
    _set_due_now(session_factory, outbox_id)
    transport_job.process_outbox_delivery(outbox_id)

    with session_factory.create_session() as session:
        row = session.query(TransportOutboxRecord).filter(TransportOutboxRecord.id == outbox_id).first()
        assert row is not None
        assert row.status == "dead"
        assert row.attempts == 3
        assert row.last_error_code == "webhook_http_error"
        assert row.last_error_message == "HTTP 404"

    assert fake_queue.calls[:2] == [5, 20]


def test_terminal_webhook_failure_enqueues_delivery_failure_email(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_webhook_dead_email.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    _seed_project(session_factory, "p3")

    with session_factory.create_session() as session:
        record = session.query(ProjectRecord).filter(ProjectRecord.id == "p3").first()
        assert record is not None
        record.email_enabled = True
        session.add(record)
        session.commit()

    outbox_id = _enqueue_webhook_outbox(session_factory, "p3")

    settings = transport_job.Settings(database_url=db_url, redis_url="redis://localhost:6379/15")
    monkeypatch.setattr(transport_job, "Settings", lambda: settings)
    monkeypatch.setattr(transport_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    monkeypatch.setattr(transport_job.httpx, "Client", lambda timeout: _FakeErrorClient())
    monkeypatch.setattr(transport_job, "Queue", lambda *args, **kwargs: _FakeQueue())

    with session_factory.create_session() as session:
        row = session.query(TransportOutboxRecord).filter(TransportOutboxRecord.id == outbox_id).first()
        assert row is not None
        row.max_attempts = 1
        session.add(row)
        session.commit()

    transport_job.process_outbox_delivery(outbox_id)

    with session_factory.create_session() as session:
        rows = (
            session.query(TransportOutboxRecord)
            .filter(TransportOutboxRecord.project_id == "p3")
            .order_by(TransportOutboxRecord.created_at.asc())
            .all()
        )
        assert len(rows) == 2
        failure_email = rows[1]
        assert failure_email.kind == "email"
        assert failure_email.event_type == "webhook.delivery_failed"
        assert failure_email.template == "webhook_delivery_failed"
        assert failure_email.payload["status"] == "dead"
        assert failure_email.payload["last_error_code"] == "webhook_http_error"


def test_terminal_webhook_test_failure_does_not_enqueue_delivery_failure_email(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite:///{tmp_path}/transport_webhook_test_dead_email.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    _seed_project(session_factory, "p4")

    with session_factory.create_session() as session:
        record = session.query(ProjectRecord).filter(ProjectRecord.id == "p4").first()
        assert record is not None
        record.email_enabled = True
        session.add(record)
        session.commit()

    service = TransportService(
        outbox_repository=TransportOutboxRepositoryImpl(session_factory=session_factory),
        enqueue_job=lambda outbox_id: None,
        now_provider=lambda: datetime.now(timezone.utc),
    )
    outbox_id = service.enqueue(
        project_id="p4",
        kind="webhook",
        event_type="webhook.test",
        payload={"body": {"event": "webhook.test", "project_id": "p4"}},
        dedupe_key="webhook-test-terminal-failure",
        destination="https://example.test/hook",
    )

    settings = transport_job.Settings(database_url=db_url, redis_url="redis://localhost:6379/15")
    monkeypatch.setattr(transport_job, "Settings", lambda: settings)
    monkeypatch.setattr(transport_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    monkeypatch.setattr(transport_job.httpx, "Client", lambda timeout: _FakeErrorClient())
    monkeypatch.setattr(transport_job, "Queue", lambda *args, **kwargs: _FakeQueue())

    with session_factory.create_session() as session:
        row = session.query(TransportOutboxRecord).filter(TransportOutboxRecord.id == outbox_id).first()
        assert row is not None
        row.max_attempts = 1
        session.add(row)
        session.commit()

    transport_job.process_outbox_delivery(outbox_id)

    with session_factory.create_session() as session:
        rows = (
            session.query(TransportOutboxRecord)
            .filter(TransportOutboxRecord.project_id == "p4")
            .order_by(TransportOutboxRecord.created_at.asc())
            .all()
        )
        assert len(rows) == 1
        assert rows[0].event_type == "webhook.test"
