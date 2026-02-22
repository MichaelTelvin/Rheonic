from datetime import datetime, timezone

import pytest

from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base, ProjectRecord
from app.infrastructure.jobs import webhook_job


class _FakeResponse:
    status_code = 200
    text = "ok"

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    def __init__(self, captured: dict[str, object]) -> None:
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb

    def post(self, url: str, content: bytes, headers: dict[str, str]):
        self._captured["url"] = url
        self._captured["content"] = content
        self._captured["headers"] = headers
        return _FakeResponse()


def test_send_project_webhook_sets_signature_and_success_status(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite:///{tmp_path}/webhook_job_test.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    now = datetime.now(timezone.utc)
    with session_factory.create_session() as session:
        session.add(
            ProjectRecord(
                id="p1",
                name="P1",
                user_id="u1",
                protect_enabled=False,
                protect_fail_mode="open",
                protect_max_req_per_min=None,
                protect_max_tok_per_min=None,
                protect_decision_timeout_ms=100,
                webhook_enabled=True,
                webhook_url="https://example.test/hook",
                webhook_secret="abc123",
                created_at=now,
            )
        )
        session.commit()

    monkeypatch.setattr(webhook_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    captured: dict[str, object] = {}
    monkeypatch.setattr(webhook_job.httpx, "Client", lambda timeout: _FakeClient(captured))

    webhook_job.send_project_webhook(
        project_id="p1",
        payload={"event": "incident.high", "project_id": "p1"},
        event_type="incident.high",
    )

    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["X-LLMTBG-Event-Type"] == "incident.high"
    assert headers["X-LLMTBG-Signature"].startswith("sha256=")

    with session_factory.create_session() as session:
        project = session.query(ProjectRecord).filter(ProjectRecord.id == "p1").first()
        assert project is not None
        assert project.webhook_last_status == "success"
        assert project.webhook_last_at is not None
        assert project.webhook_last_error is None


def test_send_project_webhook_force_send_uses_override_when_disabled(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite:///{tmp_path}/webhook_job_force_test.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    now = datetime.now(timezone.utc)
    with session_factory.create_session() as session:
        session.add(
            ProjectRecord(
                id="p2",
                name="P2",
                user_id="u1",
                protect_enabled=False,
                protect_fail_mode="open",
                protect_max_req_per_min=None,
                protect_max_tok_per_min=None,
                protect_decision_timeout_ms=100,
                webhook_enabled=False,
                webhook_url="https://saved.test/hook",
                webhook_secret="saved-secret",
                created_at=now,
            )
        )
        session.commit()

    monkeypatch.setattr(webhook_job, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    captured: dict[str, object] = {}
    monkeypatch.setattr(webhook_job.httpx, "Client", lambda timeout: _FakeClient(captured))

    webhook_job.send_project_webhook(
        project_id="p2",
        payload={"event": "webhook.test", "project_id": "p2"},
        event_type="webhook.test",
        override_url="https://draft.test/hook",
        override_secret="draft-secret",
        force_send=True,
    )

    assert captured["url"] == "https://draft.test/hook"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["X-LLMTBG-Event-Type"] == "webhook.test"
    assert headers["X-LLMTBG-Signature"].startswith("sha256=")
