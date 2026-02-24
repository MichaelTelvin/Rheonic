# Tests for policy-gap detection on first-seen provider/model tuples.
from datetime import datetime, timezone
from uuid import uuid4

from app.application.services.ingest_event_service import IngestEventService
from app.domain.models.event import Event
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base, IncidentRecord, ProjectModelRecord, ProjectRecord
from app.infrastructure.db.repositories.incident_repository_impl import IncidentRepositoryImpl
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl


class FakeEventRepository:
    # Minimal event repository used for ingest service tests.

    def add(self, event: Event) -> None:
        _ = event

    def list_recent(self, project_id: str, limit: int = 100) -> list[Event]:
        _ = project_id, limit
        return []

    def purge_older_than(self, cutoff: datetime) -> int:
        _ = cutoff
        return 0


class FakeRealtimeCounterStore:
    # Minimal counter store to keep ingest path deterministic.

    def __init__(self) -> None:
        self._requests_60s = 0
        self._tokens_60s = 0
        self._baseline_req_60s = 1.0
        self._baseline_tok_60s = 1.0

    def increment_project_60s(self, project_id: str, total_tokens: int) -> None:
        _ = project_id
        self._requests_60s += 1
        self._tokens_60s += max(int(total_tokens), 0)

    def get_project_60s(self, project_id: str) -> tuple[int, int]:
        _ = project_id
        return self._requests_60s, self._tokens_60s

    def record_baseline_snapshot(
        self,
        project_id: str,
        requests_60s: int,
        tokens_60s: int,
        max_windows: int,
    ) -> tuple[float, float]:
        _ = project_id, max_windows
        self._baseline_req_60s = max(float(requests_60s), 1.0)
        self._baseline_tok_60s = max(float(tokens_60s), 1.0)
        return self._baseline_req_60s, self._baseline_tok_60s

    def get_baseline_snapshot(self, project_id: str, max_windows: int) -> tuple[float, float]:
        _ = project_id, max_windows
        return self._baseline_req_60s, self._baseline_tok_60s

    def acquire_incident_lock(self, project_id: str, incident_type: str, ttl_seconds: int) -> bool:
        _ = project_id, incident_type, ttl_seconds
        return True

    def release_incident_lock(self, project_id: str, incident_type: str) -> None:
        _ = project_id, incident_type

    def record_incident_escalation_hit(
        self,
        project_id: str,
        incident_type: str,
        ts_unix: int,
        score: int,
        ratio: float,
        prune_before_unix: int,
        ttl_seconds: int,
    ) -> list[dict[str, object]]:
        _ = project_id, incident_type, ts_unix, score, ratio, prune_before_unix, ttl_seconds
        return []


class FakeWebhookDispatcher:
    # Captures enqueue calls for assertions.

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], str]] = []

    def enqueue(self, project_id: str, payload: dict[str, object], event_type: str) -> None:
        self.calls.append((project_id, payload, event_type))


def _setup_db(tmp_path) -> DatabaseSessionFactory:
    db_url = f"sqlite:///{tmp_path}/policy_gap_ingest.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    return session_factory


def _seed_project(session_factory: DatabaseSessionFactory, *, protect_enabled: bool) -> None:
    now = datetime.now(timezone.utc)
    with session_factory.create_session() as session:
        session.add(
            ProjectRecord(
                id="p1",
                name="Policy Gap Project",
                user_id="u1",
                protect_enabled=protect_enabled,
                protect_fail_mode="open",
                protect_max_req_per_min=None,
                protect_max_tok_per_min=None,
                protect_decision_timeout_ms=100,
                created_at=now,
            )
        )
        session.commit()


def _build_event(*, provider: str = "openai", model: str = "gpt-4o-new") -> Event:
    now = datetime.now(timezone.utc)
    return Event(
        id=str(uuid4()),
        ts=now,
        project_id="p1",
        provider=provider,
        model=model,
        environment="prod",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        latency_ms=100,
        status="ok",
        error_type=None,
        http_status=200,
        created_at=now,
    )


def _make_service(
    *,
    session_factory: DatabaseSessionFactory,
    webhook_dispatcher: FakeWebhookDispatcher | None = None,
) -> IngestEventService:
    return IngestEventService(
        event_repository=FakeEventRepository(),  # type: ignore[arg-type]
        realtime_counters=FakeRealtimeCounterStore(),  # type: ignore[arg-type]
        incident_repository=IncidentRepositoryImpl(session_factory=session_factory),
        incident_severity_cache=None,
        baseline_window_count=30,
        incident_dedup_window_seconds=300,
        webhook_dispatcher=webhook_dispatcher,  # type: ignore[arg-type]
        project_repository=ProjectRepositoryImpl(session_factory=session_factory),
    )


def test_new_model_triggers_policy_gap_incident(tmp_path) -> None:
    session_factory = _setup_db(tmp_path)
    _seed_project(session_factory, protect_enabled=True)
    service = _make_service(session_factory=session_factory)

    service.ingest(_build_event(provider="openai", model="gpt-4o-initial"))
    service.ingest(_build_event(provider="openai", model="gpt-4o-new"))

    with session_factory.create_session() as session:
        models_count = session.query(ProjectModelRecord).count()
        incidents = (
            session.query(IncidentRecord)
            .filter(IncidentRecord.project_id == "p1")
            .filter(IncidentRecord.type == "policy_gap")
            .all()
        )
    assert models_count == 2
    assert len(incidents) == 1
    assert incidents[0].severity == "low"
    assert incidents[0].provider == "openai"


def test_same_model_again_does_not_create_new_incident(tmp_path) -> None:
    session_factory = _setup_db(tmp_path)
    _seed_project(session_factory, protect_enabled=True)
    service = _make_service(session_factory=session_factory)
    service.ingest(_build_event(provider="openai", model="gpt-4o-initial"))
    event = _build_event(provider="openai", model="gpt-4o-reuse")

    service.ingest(event)
    service.ingest(_build_event(provider="openai", model="gpt-4o-reuse"))

    with session_factory.create_session() as session:
        models_count = (
            session.query(ProjectModelRecord)
            .filter(ProjectModelRecord.project_id == "p1")
            .filter(ProjectModelRecord.provider == "openai")
            .filter(ProjectModelRecord.model == "gpt-4o-reuse")
            .count()
        )
        incidents_count = (
            session.query(IncidentRecord)
            .filter(IncidentRecord.project_id == "p1")
            .filter(IncidentRecord.type == "policy_gap")
            .count()
        )
    assert models_count == 1
    assert incidents_count == 1


def test_first_model_does_not_create_policy_gap_incident_or_webhook(tmp_path) -> None:
    session_factory = _setup_db(tmp_path)
    _seed_project(session_factory, protect_enabled=True)
    dispatcher = FakeWebhookDispatcher()
    service = _make_service(session_factory=session_factory, webhook_dispatcher=dispatcher)

    service.ingest(_build_event(provider="openai", model="gpt-4o-first"))

    with session_factory.create_session() as session:
        models_count = (
            session.query(ProjectModelRecord)
            .filter(ProjectModelRecord.project_id == "p1")
            .filter(ProjectModelRecord.provider == "openai")
            .filter(ProjectModelRecord.model == "gpt-4o-first")
            .count()
        )
        incidents_count = (
            session.query(IncidentRecord)
            .filter(IncidentRecord.project_id == "p1")
            .filter(IncidentRecord.type == "policy_gap")
            .count()
        )
    assert models_count == 1
    assert incidents_count == 0
    assert dispatcher.calls == []


def test_protect_disabled_records_model_without_policy_gap_incident(tmp_path) -> None:
    session_factory = _setup_db(tmp_path)
    _seed_project(session_factory, protect_enabled=False)
    service = _make_service(session_factory=session_factory)

    service.ingest(_build_event(provider="anthropic", model="claude-new"))

    with session_factory.create_session() as session:
        models_count = (
            session.query(ProjectModelRecord)
            .filter(ProjectModelRecord.project_id == "p1")
            .filter(ProjectModelRecord.provider == "anthropic")
            .filter(ProjectModelRecord.model == "claude-new")
            .count()
        )
        incidents_count = (
            session.query(IncidentRecord)
            .filter(IncidentRecord.project_id == "p1")
            .filter(IncidentRecord.type == "policy_gap")
            .count()
        )
    assert models_count == 1
    assert incidents_count == 0


def test_webhook_dispatched_on_policy_gap(tmp_path) -> None:
    session_factory = _setup_db(tmp_path)
    _seed_project(session_factory, protect_enabled=True)
    dispatcher = FakeWebhookDispatcher()
    service = _make_service(session_factory=session_factory, webhook_dispatcher=dispatcher)

    service.ingest(_build_event(provider="openai", model="gpt-4o-initial"))
    service.ingest(_build_event(provider="google", model="gemini-new"))

    assert len(dispatcher.calls) == 1
    project_id, payload, event_type = dispatcher.calls[0]
    assert project_id == "p1"
    assert event_type == "policy_gap.detected"
    assert payload["event"] == "policy_gap.detected"
    assert payload["provider"] == "google"
    assert payload["model"] == "gemini-new"
    assert isinstance(payload.get("incident_id"), str)
