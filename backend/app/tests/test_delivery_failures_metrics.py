from datetime import datetime, timedelta, timezone

from app.application.services.metrics_service import MetricsService
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base
from app.infrastructure.db.repositories.transport_outbox_repository_impl import TransportOutboxRepositoryImpl


class _FakeRealtimeCounters:
    def get_project_60s(self, project_id: str) -> tuple[int, int]:
        _ = project_id
        return (0, 0)


class _FakeProtectActionStore:
    def get_metrics(self, project_id: str) -> dict[str, object]:
        _ = project_id
        return {}

    def get_health(self, project_id: str) -> dict[str, object]:
        _ = project_id
        return {}


class _FakeProjectRepository:
    def list_project_providers(self, project_id: str) -> list[str]:
        _ = project_id
        return []


class _FrozenDateTime(datetime):
    _current = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def set_current(cls, value: datetime) -> None:
        cls._current = value

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls._current.replace(tzinfo=None)
        return cls._current.astimezone(tz)


def test_get_delivery_failures_returns_zero_without_outbox_repo() -> None:
    service = MetricsService(
        realtime_counters=_FakeRealtimeCounters(),
        protect_action_store=_FakeProtectActionStore(),
        project_repository=_FakeProjectRepository(),
        transport_outbox_repository=None,
    )
    payload = service.get_delivery_failures(project_id="p1", kind="webhook")
    assert payload == {"count": 0, "last_attempt_at": None}


def test_get_delivery_failures_counts_failed_and_dead_and_ignores_delivered(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path}/delivery_failures_metrics.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    outbox_repo = TransportOutboxRepositoryImpl(session_factory=session_factory)

    base = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    first, _ = outbox_repo.create_or_get_deduped(
        project_id="p1",
        kind="webhook",
        event_type="incident.warn",
        destination="https://example.test/hook",
        subject=None,
        template=None,
        payload={"event": "incident.warn"},
        dedupe_key="d1",
        max_attempts=3,
        now=base,
    )
    second, _ = outbox_repo.create_or_get_deduped(
        project_id="p1",
        kind="webhook",
        event_type="protection.block",
        destination="https://example.test/hook",
        subject=None,
        template=None,
        payload={"event": "protection.block"},
        dedupe_key="d2",
        max_attempts=3,
        now=base + timedelta(seconds=1),
    )
    third, _ = outbox_repo.create_or_get_deduped(
        project_id="p1",
        kind="webhook",
        event_type="incident.resolved",
        destination="https://example.test/hook",
        subject=None,
        template=None,
        payload={"event": "incident.resolved"},
        dedupe_key="d3",
        max_attempts=3,
        now=base + timedelta(seconds=2),
    )

    outbox_repo.claim_for_send(outbox_id=first.id, now=base + timedelta(seconds=3))
    outbox_repo.mark_failed(
        outbox_id=first.id,
        now=base + timedelta(seconds=4),
        error_code="webhook_http_error",
        error_message="HTTP 500",
        next_attempt_at=base + timedelta(seconds=9),
        dead=False,
    )

    outbox_repo.claim_for_send(outbox_id=second.id, now=base + timedelta(seconds=5))
    outbox_repo.mark_delivered(outbox_id=second.id, now=base + timedelta(seconds=6))

    outbox_repo.claim_for_send(outbox_id=third.id, now=base + timedelta(seconds=7))
    outbox_repo.mark_failed(
        outbox_id=third.id,
        now=base + timedelta(seconds=8),
        error_code="timeout",
        error_message="timed out",
        next_attempt_at=None,
        dead=True,
    )

    service = MetricsService(
        realtime_counters=_FakeRealtimeCounters(),
        protect_action_store=_FakeProtectActionStore(),
        project_repository=_FakeProjectRepository(),
        transport_outbox_repository=outbox_repo,
    )

    _FrozenDateTime.set_current(base + timedelta(minutes=10))
    monkeypatch.setattr("app.application.services.metrics_service.datetime", _FrozenDateTime)

    payload = service.get_delivery_failures(project_id="p1", kind="webhook")
    assert payload["count"] == 2
    assert payload["last_attempt_at"] is not None
    assert str(payload["last_attempt_at"]).startswith("2026-03-17T12:00:08")


def test_get_delivery_failures_ignores_webhook_tests(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path}/delivery_failures_metrics_ignore_test.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    outbox_repo = TransportOutboxRepositoryImpl(session_factory=session_factory)

    base = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    test_row, _ = outbox_repo.create_or_get_deduped(
        project_id="p1",
        kind="webhook",
        event_type="webhook.test",
        destination="https://example.test/hook",
        subject=None,
        template=None,
        payload={"event": "webhook.test"},
        dedupe_key="webhook-test-row",
        max_attempts=1,
        now=base,
    )
    real_row, _ = outbox_repo.create_or_get_deduped(
        project_id="p1",
        kind="webhook",
        event_type="incident.warn",
        destination="https://example.test/hook",
        subject=None,
        template=None,
        payload={"event": "incident.warn"},
        dedupe_key="real-webhook-row",
        max_attempts=1,
        now=base + timedelta(seconds=1),
    )

    outbox_repo.claim_for_send(outbox_id=test_row.id, now=base + timedelta(seconds=2))
    outbox_repo.mark_failed(
        outbox_id=test_row.id,
        now=base + timedelta(seconds=3),
        error_code="timeout",
        error_message="timed out",
        next_attempt_at=None,
        dead=True,
    )
    outbox_repo.claim_for_send(outbox_id=real_row.id, now=base + timedelta(seconds=4))
    outbox_repo.mark_failed(
        outbox_id=real_row.id,
        now=base + timedelta(seconds=5),
        error_code="webhook_http_error",
        error_message="HTTP 500",
        next_attempt_at=None,
        dead=True,
    )

    service = MetricsService(
        realtime_counters=_FakeRealtimeCounters(),
        protect_action_store=_FakeProtectActionStore(),
        project_repository=_FakeProjectRepository(),
        transport_outbox_repository=outbox_repo,
    )

    _FrozenDateTime.set_current(base + timedelta(minutes=10))
    monkeypatch.setattr("app.application.services.metrics_service.datetime", _FrozenDateTime)

    payload = service.get_delivery_failures(project_id="p1", kind="webhook")
    assert payload["count"] == 1
    assert str(payload["last_attempt_at"]).startswith("2026-03-17T12:00:05")


def test_get_delivery_failures_uses_24h_window(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path}/delivery_failures_metrics_24h_window.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    outbox_repo = TransportOutboxRepositoryImpl(session_factory=session_factory)

    base = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    stale_row, _ = outbox_repo.create_or_get_deduped(
        project_id="p1",
        kind="webhook",
        event_type="incident.warn",
        destination="https://example.test/hook",
        subject=None,
        template=None,
        payload={"event": "incident.warn"},
        dedupe_key="stale-row",
        max_attempts=1,
        now=base - timedelta(hours=30),
    )
    fresh_row, _ = outbox_repo.create_or_get_deduped(
        project_id="p1",
        kind="webhook",
        event_type="protection.block",
        destination="https://example.test/hook",
        subject=None,
        template=None,
        payload={"event": "protection.block"},
        dedupe_key="fresh-row",
        max_attempts=1,
        now=base - timedelta(hours=2),
    )

    outbox_repo.claim_for_send(outbox_id=stale_row.id, now=base - timedelta(hours=30) + timedelta(minutes=1))
    outbox_repo.mark_failed(
        outbox_id=stale_row.id,
        now=base - timedelta(hours=29, minutes=59),
        error_code="timeout",
        error_message="timed out",
        next_attempt_at=None,
        dead=True,
    )
    outbox_repo.claim_for_send(outbox_id=fresh_row.id, now=base - timedelta(hours=2) + timedelta(minutes=1))
    outbox_repo.mark_failed(
        outbox_id=fresh_row.id,
        now=base - timedelta(hours=1, minutes=59),
        error_code="webhook_http_error",
        error_message="HTTP 500",
        next_attempt_at=None,
        dead=True,
    )

    _FrozenDateTime.set_current(base)
    monkeypatch.setattr("app.application.services.metrics_service.datetime", _FrozenDateTime)

    service = MetricsService(
        realtime_counters=_FakeRealtimeCounters(),
        protect_action_store=_FakeProtectActionStore(),
        project_repository=_FakeProjectRepository(),
        transport_outbox_repository=outbox_repo,
    )

    payload = service.get_delivery_failures(project_id="p1", kind="webhook")
    assert payload["count"] == 1
    assert str(payload["last_attempt_at"]).startswith("2026-03-17T10:01:00")


def test_get_delivery_failures_returns_zero_after_more_recent_success(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path}/delivery_failures_metrics_latest_success.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    outbox_repo = TransportOutboxRepositoryImpl(session_factory=session_factory)

    base = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    failed_row, _ = outbox_repo.create_or_get_deduped(
        project_id="p1",
        kind="webhook",
        event_type="policy_gap.detected",
        destination="https://example.test/hook",
        subject=None,
        template=None,
        payload={"event": "policy_gap.detected"},
        dedupe_key="failed-row",
        max_attempts=1,
        now=base,
    )
    success_row, _ = outbox_repo.create_or_get_deduped(
        project_id="p1",
        kind="webhook",
        event_type="policy_gap.detected",
        destination="https://example.test/hook",
        subject=None,
        template=None,
        payload={"event": "policy_gap.detected"},
        dedupe_key="success-row",
        max_attempts=1,
        now=base + timedelta(minutes=5),
    )

    outbox_repo.claim_for_send(outbox_id=failed_row.id, now=base + timedelta(seconds=1))
    outbox_repo.mark_failed(
        outbox_id=failed_row.id,
        now=base + timedelta(seconds=2),
        error_code="webhook_http_error",
        error_message="HTTP 500",
        next_attempt_at=None,
        dead=True,
    )
    outbox_repo.claim_for_send(outbox_id=success_row.id, now=base + timedelta(minutes=5, seconds=1))
    outbox_repo.mark_delivered(outbox_id=success_row.id, now=base + timedelta(minutes=5, seconds=2))

    service = MetricsService(
        realtime_counters=_FakeRealtimeCounters(),
        protect_action_store=_FakeProtectActionStore(),
        project_repository=_FakeProjectRepository(),
        transport_outbox_repository=outbox_repo,
    )

    _FrozenDateTime.set_current(base + timedelta(minutes=10))
    monkeypatch.setattr("app.application.services.metrics_service.datetime", _FrozenDateTime)

    payload = service.get_delivery_failures(project_id="p1", kind="webhook")
    assert payload == {"count": 0, "last_attempt_at": None}
