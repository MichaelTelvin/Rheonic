from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.application.services.auto_close_incidents_service import AutoCloseIncidentsService
from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.protect_service import ProtectService
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base, IncidentRecord, IngestKeyRecord, ProjectRecord, UserRecord
from app.infrastructure.db.repositories.incident_repository_impl import IncidentRepositoryImpl
from app.infrastructure.db.repositories.ingest_key_repository_impl import IngestKeyRepositoryImpl
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.infrastructure.redis.protect_action_store import ProtectActionStore
from app.infrastructure.redis.rolling_window import RollingWindow
from app.security.ingest_keys import hash_key, last4


class FakeRedisClient:
    # In-memory fake Redis adapter for rolling-window/protect-action calls.

    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.zsets: dict[str, dict[str, int]] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> object | None:
        return self.values.get(key)

    def set(self, key: str, value: object, ex: int | None = None) -> bool:
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def set_persistent(self, key: str, value: object) -> None:
        self.values[key] = value

    def incr(self, key: str) -> int:
        next_value = int(self.values.get(key, 0)) + 1
        self.values[key] = next_value
        return next_value

    def expire(self, key: str, ttl_seconds: int) -> bool:
        self.ttls[key] = ttl_seconds
        return True

    def zadd(self, key: str, mapping: dict[str, int]) -> int:
        zset = self.zsets.setdefault(key, {})
        added = 0
        for member, score in mapping.items():
            if member not in zset:
                added += 1
            zset[member] = score
        return added

    def zremrangebyscore(self, key: str, min_score: int | float, max_score: int | float) -> int:
        zset = self.zsets.get(key, {})
        to_delete = [member for member, score in zset.items() if float(min_score) <= score <= float(max_score)]
        for member in to_delete:
            del zset[member]
        return len(to_delete)

    def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, {}))

    def zrangebyscore(self, key: str, min_score: int | float, max_score: int | float) -> list[object]:
        zset = self.zsets.get(key, {})
        upper = float("inf") if max_score == float("inf") else float(max_score)
        selected = [(member, score) for member, score in zset.items() if float(min_score) <= score <= upper]
        selected.sort(key=lambda item: (item[1], item[0]))
        return [member.encode("utf-8") for member, _ in selected]


class FakeWebhookDispatcher:
    # Captures webhook dispatcher enqueue calls.

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], str]] = []

    def enqueue(
        self,
        project_id: str,
        payload: dict[str, object],
        event_type: str,
        *,
        override_url: str | None = None,
        override_secret: str | None = None,
        force_send: bool = False,
    ) -> None:
        _ = (override_url, override_secret, force_send)
        self.calls.append((project_id, payload, event_type))


def _setup_db(tmp_path) -> DatabaseSessionFactory:
    db_url = f"sqlite:///{tmp_path}/incident_auto_close.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    return session_factory


def test_auto_close_resolves_only_stale_open_incidents(tmp_path) -> None:
    session_factory = _setup_db(tmp_path)
    now = datetime.now(timezone.utc)
    old_seen = now - timedelta(minutes=20)
    recent_seen = now - timedelta(seconds=30)

    with session_factory.create_session() as session:
        session.add(
            IncidentRecord(
                id="inc-old",
                project_id="p1",
                provider="openai",
                type="retry_storm",
                status="open",
                evidence={},
                created_at=old_seen,
                last_seen_at=old_seen,
                resolved_at=None,
            )
        )
        session.add(
            IncidentRecord(
                id="inc-recent",
                project_id="p1",
                provider="openai",
                type="loop_suspect",
                status="open",
                evidence={},
                created_at=recent_seen,
                last_seen_at=recent_seen,
                resolved_at=None,
            )
        )
        session.commit()

    service = AutoCloseIncidentsService(
        incident_repository=IncidentRepositoryImpl(session_factory=session_factory),
        cooldown_seconds=300,
    )
    resolved_count = service.auto_close(now=now)
    assert resolved_count == 1

    with session_factory.create_session() as session:
        old_record = session.query(IncidentRecord).filter(IncidentRecord.id == "inc-old").first()
        recent_record = session.query(IncidentRecord).filter(IncidentRecord.id == "inc-recent").first()
        assert old_record is not None
        assert old_record.status == "auto_resolved"
        assert old_record.resolved_at is not None
        assert recent_record is not None
        assert recent_record.status == "open"
        assert recent_record.resolved_at is None


def test_protect_decision_ignores_auto_resolved_incidents(tmp_path) -> None:
    session_factory = _setup_db(tmp_path)
    now = datetime.now(timezone.utc)
    old_seen = now - timedelta(minutes=10)
    plaintext_ingest_key = "k_test_auto_close"
    project_id = "p-protect"

    with session_factory.create_session() as session:
        session.add(
            UserRecord(
                id="u1",
                email="autoclose@example.com",
                password_hash="hashed",
                created_at=now,
            )
        )
        session.add(
            ProjectRecord(
                id=project_id,
                name="Protect Auto Close",
                user_id="u1",
                protect_enabled=True,
                protect_fail_mode="open",
                protect_max_req_per_min=None,
                protect_max_tok_per_min=None,
                created_at=now,
            )
        )
        session.add(
            IngestKeyRecord(
                id=str(uuid4()),
                project_id=project_id,
                name="dev",
                key_hash=hash_key(plaintext_ingest_key),
                last4=last4(plaintext_ingest_key),
                status="active",
                created_at=now,
                revoked_at=None,
            )
        )
        session.add(
            IncidentRecord(
                id="inc-stale",
                project_id=project_id,
                provider="openai",
                type="cap_breach",
                status="open",
                evidence={},
                created_at=old_seen,
                last_seen_at=old_seen,
                resolved_at=None,
            )
        )
        session.commit()

    redis_client = FakeRedisClient()
    auto_close_service = AutoCloseIncidentsService(
        incident_repository=IncidentRepositoryImpl(session_factory=session_factory),
        cooldown_seconds=300,
    )
    resolved_count = auto_close_service.auto_close(now=now)
    assert resolved_count == 1

    protect_service = ProtectService(
        ingest_key_service=IngestKeyService(
            ingest_key_repository=IngestKeyRepositoryImpl(session_factory=session_factory),
            project_repository=ProjectRepositoryImpl(session_factory=session_factory),
        ),
        realtime_counters=RollingWindow(client=redis_client, now_ms_provider=lambda: int(now.timestamp() * 1000)),
        protect_action_store=ProtectActionStore(redis_client=redis_client),  # type: ignore[arg-type]
        protect_block_cooldown_seconds=60,
    )
    _, decision = protect_service.evaluate_decision(ingest_key=plaintext_ingest_key)
    assert decision is not None
    assert decision.decision == "allow"
    assert decision.reason == "ok"


def test_auto_close_enqueues_incident_resolved_webhook(tmp_path) -> None:
    session_factory = _setup_db(tmp_path)
    now = datetime.now(timezone.utc)
    old_seen = now - timedelta(minutes=20)
    dispatcher = FakeWebhookDispatcher()

    with session_factory.create_session() as session:
        session.add(
            ProjectRecord(
                id="p1",
                name="AutoClose",
                user_id="u1",
                protect_enabled=True,
                protect_fail_mode="open",
                protect_max_req_per_min=None,
                protect_max_tok_per_min=None,
                created_at=now,
            )
        )
        session.add(
            IncidentRecord(
                id="inc-old-webhook",
                project_id="p1",
                provider="openai",
                type="retry_storm",
                status="open",
                evidence={"provider": "openai", "model": "gpt-4o-mini", "environment": "prod"},
                created_at=old_seen,
                last_seen_at=old_seen,
                resolved_at=None,
            )
        )
        session.commit()

    service = AutoCloseIncidentsService(
        incident_repository=IncidentRepositoryImpl(session_factory=session_factory),
        cooldown_seconds=300,
        webhook_dispatcher=dispatcher,  # type: ignore[arg-type]
        project_repository=ProjectRepositoryImpl(session_factory=session_factory),
    )
    resolved_count = service.auto_close(now=now)
    assert resolved_count == 1
    assert len(dispatcher.calls) == 1
    _, payload, event_type = dispatcher.calls[0]
    assert event_type == "incident.resolved"
    assert payload["event"] == "incident.resolved"
    assert payload["resolved_by"] == "auto"
    assert payload["incident_id"] == "inc-old-webhook"
