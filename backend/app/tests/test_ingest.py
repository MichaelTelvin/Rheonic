from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.application.services.ingest_event_service import IngestEventService
from app.domain.models.event import Event
from app.domain.models.incident import Incident
from app.domain.models.project import Project


class FakeRealtimeCounterStore:
    def __init__(self) -> None:
        self.values: dict[str, tuple[int, int]] = {}

    def increment_project_60s(self, project_id: str, total_tokens: int) -> None:
        req, tok = self.values.get(project_id, (0, 0))
        self.values[project_id] = (req + 1, tok + int(total_tokens))

    def get_project_60s(self, project_id: str) -> tuple[int, int]:
        return self.values.get(project_id, (0, 0))

    def acquire_incident_lock(self, project_id: str, incident_type: str, ttl_seconds: int) -> bool:
        _ = (project_id, incident_type, ttl_seconds)
        return True

    def release_incident_lock(self, project_id: str, incident_type: str) -> None:
        _ = (project_id, incident_type)


class FakeEventRepository:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def add(self, event: Event) -> None:
        self.events.append(event)

    def list_recent(self, project_id: str, limit: int = 100) -> list[Event]:
        return [event for event in self.events if event.project_id == project_id][-limit:]

    def purge_older_than(self, cutoff: datetime) -> int:
        before = len(self.events)
        self.events = [event for event in self.events if event.created_at >= cutoff]
        return before - len(self.events)


class FakeIncidentRepository:
    def __init__(self) -> None:
        self.rows: list[Incident] = []

    def create_incident(self, incident: Incident) -> Incident:
        self.rows.append(incident)
        return incident

    def get_open_incident_by_type(self, project_id: str, provider: str, incident_type: str) -> Incident | None:
        for row in reversed(self.rows):
            if row.project_id == project_id and row.provider == provider and row.incident_type == incident_type and row.status == "open":
                return row
        return None

    def get_open_incident_by_fingerprint(self, project_id: str, provider: str, fingerprint: str, created_after: datetime) -> Incident | None:
        for row in reversed(self.rows):
            if (
                row.project_id == project_id
                and row.provider == provider
                and row.fingerprint == fingerprint
                and row.status == "open"
                and row.created_at >= created_after
            ):
                return row
        return None

    def update_open_incident_activity(self, incident_id: str, evidence: dict[str, object], last_seen_at: datetime) -> Incident | None:
        for row in self.rows:
            if row.id == incident_id and row.status == "open":
                row.evidence = evidence
                row.last_seen_at = last_seen_at
                return row
        return None

    def list_by_project(self, project_id: str, status: str = "open", provider: str | None = None) -> list[Incident]:
        return [
            row
            for row in self.rows
            if row.project_id == project_id
            and (status == "all" or row.status == status)
            and (provider is None or row.provider == provider)
        ]

    def list_open_by_project_provider(self, project_id: str, provider: str) -> list[Incident]:
        return [row for row in self.rows if row.project_id == project_id and row.provider == provider and row.status == "open"]

    def get_by_id(self, incident_id: str) -> Incident | None:
        for row in self.rows:
            if row.id == incident_id:
                return row
        return None

    def resolve_incident(self, incident_id: str) -> Incident | None:
        row = self.get_by_id(incident_id)
        if row is None:
            return None
        row.status = "resolved"
        row.resolved_at = datetime.now(timezone.utc)
        return row

    def auto_resolve_stale_open_incidents(self, *, cutoff: datetime, resolved_at: datetime) -> tuple[list[Incident], set[tuple[str, str]]]:
        _ = cutoff
        resolved: list[Incident] = []
        pairs: set[tuple[str, str]] = set()
        for row in self.rows:
            if row.status == "open":
                row.status = "auto_resolved"
                row.resolved_at = resolved_at
                resolved.append(row)
                pairs.add((row.project_id, row.provider))
        return resolved, pairs


class FakeWebhookDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

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
        self.calls.append((project_id, event_type, payload))


class FakeProjectRepository:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.seen: set[tuple[str, str, str]] = set()

    def get_project(self, project_id: str) -> Project | None:
        return self.project if self.project.id == project_id else None

    def record_project_model_first_seen(self, *, project_id: str, provider: str, model: str, first_seen_at: datetime) -> bool:
        _ = first_seen_at
        key = (project_id, provider, model)
        if key in self.seen:
            return False
        self.seen.add(key)
        return True

    # Unused interface methods.
    def list_projects(self) -> list[Project]:
        return [self.project]

    def list_projects_for_user(self, user_id: str) -> list[Project]:
        _ = user_id
        return [self.project]

    def create_project(self, project: Project) -> Project:
        self.project = project
        return project

    def get_project_by_name(self, name: str) -> Project | None:
        _ = name
        return None

    def get_project_by_name_for_user(self, name: str, user_id: str) -> Project | None:
        _ = (name, user_id)
        return None

    def update_project_protect_settings(
        self,
        project_id: str,
        protect_enabled: bool,
        protect_fail_mode: str,
        apply_clamp: bool,
        protect_max_req_per_min: int | None,
        protect_max_tok_per_min: int | None,
        protect_decision_timeout_ms: int,
    ) -> Project | None:
        if project_id != self.project.id:
            return None
        self.project.protect_enabled = protect_enabled
        self.project.protect_fail_mode = protect_fail_mode
        self.project.apply_clamp = apply_clamp
        self.project.protect_max_req_per_min = protect_max_req_per_min
        self.project.protect_max_tok_per_min = protect_max_tok_per_min
        self.project.protect_decision_timeout_ms = protect_decision_timeout_ms
        return self.project

    def update_project_webhook_settings(
        self,
        project_id: str,
        webhook_enabled: bool,
        webhook_url: str | None,
        webhook_secret: str | None,
    ) -> Project | None:
        _ = (project_id, webhook_enabled, webhook_url, webhook_secret)
        return self.project

    def update_project_webhook_delivery_status(
        self,
        project_id: str,
        status: str,
        at: datetime,
        error: str | None,
    ) -> Project | None:
        _ = (project_id, status, at, error)
        return self.project

    def count_project_models(self, project_id: str) -> int:
        _ = project_id
        return len(self.seen)

    def list_project_providers(self, project_id: str) -> list[str]:
        _ = project_id
        return sorted({provider for _, provider, _ in self.seen})


def _event(
    project_id: str,
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    *,
    total_tokens: int = 100,
    status: str = "ok",
    http_status: int = 200,
    error_type: str | None = None,
    endpoint: str = "/chat/completions",
    feature: str | None = "demo",
    offset_seconds: int = 0,
) -> Event:
    now = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return Event(
        id=f"evt-{project_id}-{provider}-{model}-{offset_seconds}-{total_tokens}",
        ts=now,
        project_id=project_id,
        provider=provider,
        model=model,
        environment="dev",
        input_tokens=max(total_tokens // 2, 1),
        output_tokens=max(total_tokens // 2, 1),
        total_tokens=total_tokens,
        latency_ms=120,
        status=status,
        error_type=error_type,
        http_status=http_status,
        request_endpoint=endpoint,
        request_feature=feature,
        created_at=now,
    )


def _service(*, protect_enabled: bool, req_cap: int | None = None, tok_cap: int | None = None, retry_storm_count: int = 3, loop_count: int = 6, token_explosion_abs: int = 6000) -> tuple[IngestEventService, FakeIncidentRepository, FakeWebhookDispatcher]:
    incidents = FakeIncidentRepository()
    webhook = FakeWebhookDispatcher()
    service = IngestEventService(
        event_repository=FakeEventRepository(),
        realtime_counters=FakeRealtimeCounterStore(),
        incident_repository=incidents,
        incident_dedup_window_seconds=300,
        webhook_dispatcher=webhook,
        project_repository=FakeProjectRepository(
            Project(
                id="p1",
                name="P1",
                user_id="u1",
                created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                protect_enabled=protect_enabled,
                protect_max_req_per_min=req_cap,
                protect_max_tok_per_min=tok_cap,
            )
        ),
        retry_storm_count=retry_storm_count,
        retry_storm_window_seconds=60,
        loop_count=loop_count,
        loop_window_seconds=30,
        token_explosion_abs=token_explosion_abs,
        token_explosion_ratio=0.8,
    )
    return service, incidents, webhook


def test_retry_storm_opens_incident_and_updates_dedup_count() -> None:
    service, incidents, webhook = _service(protect_enabled=True, retry_storm_count=2)
    service.ingest(_event("p1", status="error", http_status=502, error_type="provider_error", offset_seconds=0))
    service.ingest(_event("p1", status="error", http_status=503, error_type="provider_error", offset_seconds=1))
    service.ingest(_event("p1", status="error", http_status=504, error_type="provider_error", offset_seconds=2))

    assert len(incidents.rows) == 1
    row = incidents.rows[0]
    assert row.incident_type == "retry_storm"
    assert int(row.evidence.get("count", 0)) == 2
    assert row.status == "open"
    assert any(event_type == "incident.warn" for _, event_type, _ in webhook.calls)


def test_loop_suspect_opens_incident_in_observe_without_warn_webhook() -> None:
    service, incidents, webhook = _service(protect_enabled=False, loop_count=3)
    service.ingest(_event("p1", total_tokens=42, feature="loop-fixed-signature", offset_seconds=0))
    service.ingest(_event("p1", total_tokens=42, feature="loop-fixed-signature", offset_seconds=1))
    service.ingest(_event("p1", total_tokens=42, feature="loop-fixed-signature", offset_seconds=2))

    assert len(incidents.rows) == 1
    assert incidents.rows[0].incident_type == "loop_suspect"
    assert all(event_type not in {"incident.warn", "incident.block"} for _, event_type, _ in webhook.calls)


def test_loop_detector_ignores_error_events_and_retry_storm_still_triggers() -> None:
    service, incidents, webhook = _service(protect_enabled=True, retry_storm_count=3, loop_count=3)
    for i in range(3):
        service.ingest(
            _event(
                "p1",
                status="error",
                http_status=500,
                error_type="provider_5xx",
                feature="retry-fixed-signature",
                offset_seconds=i,
            )
        )

    assert len(incidents.rows) == 1
    assert incidents.rows[0].incident_type == "retry_storm"
    assert all(row.incident_type != "loop_suspect" for row in incidents.rows)
    assert any(event_type == "incident.warn" for _, event_type, _ in webhook.calls)


def test_loop_signature_is_scoped_by_feature() -> None:
    service, incidents, _ = _service(protect_enabled=False, loop_count=3)

    service.ingest(_event("p1", feature="feature-a", offset_seconds=0))
    service.ingest(_event("p1", feature="feature-b", offset_seconds=1))
    service.ingest(_event("p1", feature="feature-a", offset_seconds=2))

    assert all(row.incident_type != "loop_suspect" for row in incidents.rows)

    service.ingest(_event("p1", feature="feature-a", offset_seconds=3))

    loop_rows = [row for row in incidents.rows if row.incident_type == "loop_suspect"]
    assert len(loop_rows) == 1
    assert "feature-a" in str(loop_rows[0].evidence.get("signature"))


def test_cap_breach_logged_in_observe_mode() -> None:
    service, incidents, webhook = _service(protect_enabled=False, req_cap=1, tok_cap=500)
    service.ingest(_event("p1", total_tokens=100, offset_seconds=0))

    assert len(incidents.rows) == 1
    assert incidents.rows[0].incident_type == "cap_breach"
    assert incidents.rows[0].evidence.get("req_cap_breach") is True
    assert all(event_type not in {"incident.warn", "incident.block"} for _, event_type, _ in webhook.calls)


def test_cap_breach_repeated_events_update_same_incident_within_dedup_window() -> None:
    service, incidents, _ = _service(protect_enabled=False, req_cap=2, tok_cap=1000)
    service.ingest(_event("p1", provider="openai", total_tokens=10, offset_seconds=0))
    service.ingest(_event("p1", provider="openai", total_tokens=10, offset_seconds=1))
    service.ingest(_event("p1", provider="openai", total_tokens=10, offset_seconds=2))

    cap_rows = [row for row in incidents.rows if row.incident_type == "cap_breach" and row.provider == "openai"]
    assert len(cap_rows) == 1
    assert int(cap_rows[0].evidence.get("count", 0)) == 2


def test_near_cap_opens_incident_in_observe_without_webhook() -> None:
    service, incidents, webhook = _service(protect_enabled=False, req_cap=None, tok_cap=1000)
    service.ingest(_event("p1", total_tokens=600, offset_seconds=0))

    near_cap_rows = [row for row in incidents.rows if row.incident_type == "near_cap"]
    assert len(near_cap_rows) == 1
    assert all(event_type not in {"incident.warn", "incident.block"} for _, event_type, _ in webhook.calls)


def test_near_cap_in_protect_mode_does_not_emit_incident_warn_webhook() -> None:
    service, incidents, webhook = _service(protect_enabled=True, req_cap=None, tok_cap=1000)
    service.ingest(_event("p1", total_tokens=600, offset_seconds=0))

    near_cap_rows = [row for row in incidents.rows if row.incident_type == "near_cap"]
    assert len(near_cap_rows) == 1
    assert all(event_type != "incident.warn" for _, event_type, _ in webhook.calls)


def test_token_explosion_incident_emits_warn_in_protect_mode() -> None:
    service, incidents, webhook = _service(protect_enabled=True, tok_cap=10_000, token_explosion_abs=1500)
    service.ingest(_event("p1", total_tokens=1800, offset_seconds=0))

    assert len(incidents.rows) == 1
    assert incidents.rows[0].incident_type == "token_explosion"
    assert any(event_type == "incident.warn" for _, event_type, _ in webhook.calls)


def test_cap_breach_suppresses_token_explosion_for_same_event() -> None:
    service, incidents, webhook = _service(protect_enabled=True, req_cap=None, tok_cap=1000, token_explosion_abs=500)
    service.ingest(_event("p1", provider="openai", total_tokens=1200, offset_seconds=0))

    assert len(incidents.rows) == 1
    incident = incidents.rows[0]
    assert incident.provider == "openai"
    assert incident.incident_type == "cap_breach"
    assert incident.evidence.get("tok_cap_breach") is True
    assert all(row.incident_type != "token_explosion" for row in incidents.rows)
    assert all(event_type != "incident.block" for _, event_type, _ in webhook.calls)


def test_policy_gap_first_seen_webhook_only_once_and_no_incident() -> None:
    service, incidents, webhook = _service(protect_enabled=True)
    service.ingest(_event("p1", provider="openai", model="gpt-4o-mini", total_tokens=10, offset_seconds=0))
    service.ingest(_event("p1", provider="openai", model="gpt-4o-mini", total_tokens=12, offset_seconds=30))

    policy_gap_calls = [call for call in webhook.calls if call[1] == "policy_gap.detected"]
    assert len(policy_gap_calls) == 1
    assert incidents.rows == []


def test_policy_gap_webhook_not_sent_in_observe_mode() -> None:
    service, incidents, webhook = _service(protect_enabled=False)
    service.ingest(_event("p1", provider="openai", model="gpt-4o-mini", total_tokens=10, offset_seconds=0))

    assert all(event_type != "policy_gap.detected" for _, event_type, _ in webhook.calls)
    assert incidents.rows == []
