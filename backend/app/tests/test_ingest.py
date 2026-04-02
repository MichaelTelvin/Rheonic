from __future__ import annotations

from collections.abc import Callable
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

    def list_recent(self, project_id: str, limit: int = 100, provider: str | None = None) -> list[Event]:
        rows = [event for event in self.events if event.project_id == project_id]
        if provider:
            rows = [event for event in rows if event.provider == provider]
        return rows[-limit:]

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
            if (
                row.project_id == project_id
                and row.provider == provider
                and row.incident_type == incident_type
                and row.status == "open"
            ):
                return row
        return None

    def get_open_incident_by_fingerprint(
        self, project_id: str, provider: str, fingerprint: str, active_after: datetime
    ) -> Incident | None:
        for row in reversed(self.rows):
            row_active_at = row.last_seen_at or row.created_at
            if (
                row.project_id == project_id
                and row.provider == provider
                and row.fingerprint == fingerprint
                and row.status == "open"
                and row_active_at >= active_after
            ):
                return row
        return None

    def update_open_incident_activity(
        self, incident_id: str, evidence: dict[str, object], last_seen_at: datetime
    ) -> Incident | None:
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
        return [
            row
            for row in self.rows
            if row.project_id == project_id and row.provider == provider and row.status == "open"
        ]

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

    def resolve_open_incidents_by_type(
        self,
        *,
        project_id: str,
        provider: str,
        incident_type: str,
        resolved_at: datetime,
        created_after: datetime | None = None,
    ) -> list[Incident]:
        resolved: list[Incident] = []
        for row in self.rows:
            if (
                row.project_id == project_id
                and row.provider == provider
                and row.incident_type == incident_type
                and row.status == "open"
                and (created_after is None or row.created_at >= created_after)
            ):
                row.status = "resolved"
                row.resolved_at = resolved_at
                resolved.append(row)
        return resolved

    def auto_resolve_stale_open_incidents(
        self, *, cutoff: datetime, resolved_at: datetime
    ) -> tuple[list[Incident], set[tuple[str, str]]]:
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
        force_send: bool = False,
    ) -> None:
        _ = (override_url, force_send)
        self.calls.append((project_id, event_type, payload))


class FakeTransportService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def enqueue(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return "outbox-1"


class FakeProjectRepository:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.seen: set[tuple[str, str, str]] = set()

    def get_project(self, project_id: str) -> Project | None:
        return self.project if self.project.id == project_id else None

    def record_project_model_first_seen(
        self, *, project_id: str, provider: str, requested_model: str, first_seen_at: datetime
    ) -> tuple[bool, bool]:
        _ = first_seen_at
        key = (project_id, provider, requested_model)
        if key in self.seen:
            return False, True
        had_existing_models = bool(self.seen)
        self.seen.add(key)
        return True, had_existing_models

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
    ) -> Project | None:
        if project_id != self.project.id:
            return None
        self.project.protect_enabled = protect_enabled
        self.project.protect_fail_mode = protect_fail_mode
        self.project.apply_clamp = apply_clamp
        self.project.protect_max_req_per_min = protect_max_req_per_min
        self.project.protect_max_tok_per_min = protect_max_tok_per_min
        return self.project

    def update_project_webhook_settings(
        self,
        project_id: str,
        webhook_enabled: bool,
        email_enabled: bool,
        webhook_url: str | None,
    ) -> Project | None:
        _ = (project_id, webhook_enabled, email_enabled, webhook_url)
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
    requested_model: str = "gpt-4o-mini",
    *,
    total_tokens: int = 100,
    token_explosion_tokens: int | None = None,
    status: str = "ok",
    http_status: int = 200,
    error_type: str | None = None,
    error_message: str | None = None,
    endpoint: str = "/chat/completions",
    feature: str | None = "demo",
    request_fingerprint: str | None = None,
    offset_seconds: int = 0,
) -> Event:
    now = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return Event(
        id=f"evt-{project_id}-{provider}-{requested_model}-{offset_seconds}-{total_tokens}",
        ts=now,
        project_id=project_id,
        provider=provider,
        requested_model=requested_model,
        resolved_model=None,
        environment="dev",
        input_tokens=max(total_tokens // 2, 1),
        output_tokens=max(total_tokens // 2, 1),
        total_tokens=total_tokens,
        latency_ms=120,
        token_explosion_tokens=token_explosion_tokens if token_explosion_tokens is not None else total_tokens,
        status=status,
        error_type=error_type,
        error_message=error_message,
        http_status=http_status,
        request_endpoint=endpoint,
        request_feature=feature,
        request_fingerprint=request_fingerprint,
        created_at=now,
    )


def _service(
    *,
    protect_enabled: bool,
    req_cap: int | None = None,
    tok_cap: int | None = None,
    retry_storm_count: int = 3,
    loop_count: int = 6,
    loop_max_gap_seconds: float = 2.0,
    loop_concurrency_threshold: int = 5,
    token_explosion_abs: int = 10000,
    token_explosion_growth_ratio: float = 1.7,
    token_explosion_growth_count: int = 2,
    token_explosion_growth_min_tokens: int = 1800,
    token_explosion_concurrency_threshold: int = 8,
    now_provider: Callable[[], datetime] | None = None,
) -> tuple[IngestEventService, FakeIncidentRepository, FakeWebhookDispatcher, FakeTransportService]:
    incidents = FakeIncidentRepository()
    webhook = FakeWebhookDispatcher()
    transport = FakeTransportService()
    service = IngestEventService(
        event_repository=FakeEventRepository(),
        realtime_counters=FakeRealtimeCounterStore(),
        incident_repository=incidents,
        incident_dedup_window_seconds=300,
        webhook_dispatcher=webhook,
        transport_service=transport,  # type: ignore[arg-type]
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
        loop_max_gap_seconds=loop_max_gap_seconds,
        loop_concurrency_threshold=loop_concurrency_threshold,
        token_explosion_abs=token_explosion_abs,
        token_explosion_growth_ratio=token_explosion_growth_ratio,
        token_explosion_growth_count=token_explosion_growth_count,
        token_explosion_growth_min_tokens=token_explosion_growth_min_tokens,
        token_explosion_concurrency_threshold=token_explosion_concurrency_threshold,
        now_provider=now_provider,
    )
    return service, incidents, webhook, transport


def _clock(start: datetime | None = None) -> tuple[dict[str, datetime], Callable[[], datetime]]:
    state = {"now": start or datetime(2026, 3, 25, 10, 47, 0, tzinfo=timezone.utc)}

    def _now() -> datetime:
        return state["now"]

    return state, _now


def _ingest_at(service: IngestEventService, clock: dict[str, datetime], event: Event) -> None:
    clock["now"] = event.created_at
    service.ingest(event)


def _non_policy_gap_webhook_calls(
    webhook: FakeWebhookDispatcher,
) -> list[tuple[str, str, dict[str, object]]]:
    return [call for call in webhook.calls if call[1] != "policy_gap.detected"]


def test_retry_storm_opens_incident_and_updates_dedup_count() -> None:
    service, incidents, webhook, transport = _service(protect_enabled=True, retry_storm_count=2)
    service.ingest(_event("p1", status="error", http_status=502, error_type="provider_error", offset_seconds=0))
    service.ingest(_event("p1", status="error", http_status=503, error_type="provider_error", offset_seconds=1))
    service.ingest(_event("p1", status="error", http_status=504, error_type="provider_error", offset_seconds=2))

    assert len(incidents.rows) == 1
    row = incidents.rows[0]
    assert row.incident_type == "retry_storm"
    assert int(row.evidence.get("count", 0)) == 2
    assert row.status == "open"
    assert any(event_type == "incident.warn" for _, event_type, _ in webhook.calls)
    assert [call["event_type"] for call in transport.calls] == ["incident.warn"]
    assert [call["template"] for call in transport.calls] == ["incident_warn"]


def test_retry_storm_ignores_retry_status_without_failure_signal() -> None:
    service, incidents, webhook, transport = _service(protect_enabled=False, retry_storm_count=2)
    service.ingest(_event("p1", status="retry", http_status=200, offset_seconds=0))
    service.ingest(_event("p1", status="retry", http_status=200, offset_seconds=1))
    service.ingest(_event("p1", status="retry", http_status=200, offset_seconds=2))

    assert incidents.rows == []
    assert _non_policy_gap_webhook_calls(webhook) == []
    assert transport.calls == []


def test_retry_storm_does_not_double_count_retry_state_updates() -> None:
    service, incidents, webhook, transport = _service(protect_enabled=True, retry_storm_count=2)
    service.ingest(_event("p1", status="error", http_status=502, error_type="provider_error", offset_seconds=0))
    service.ingest(_event("p1", status="retry", http_status=200, offset_seconds=1))

    assert incidents.rows == []

    service.ingest(_event("p1", status="error", http_status=503, error_type="provider_error", offset_seconds=2))

    assert len(incidents.rows) == 1
    row = incidents.rows[0]
    assert row.incident_type == "retry_storm"
    assert row.evidence.get("failure_count") == 2
    assert any(event_type == "incident.warn" for _, event_type, _ in webhook.calls)
    assert [call["event_type"] for call in transport.calls] == ["incident.warn"]
    assert [call["template"] for call in transport.calls] == ["incident_warn"]


def test_retry_storm_detects_timeout_from_error_message_even_with_generic_error_type() -> None:
    service, incidents, webhook, transport = _service(protect_enabled=True, retry_storm_count=2)
    service.ingest(
        _event(
            "p1",
            status="error",
            http_status=200,
            error_type="error",
            error_message="Request timed out",
            offset_seconds=0,
        )
    )
    service.ingest(
        _event(
            "p1",
            status="error",
            http_status=200,
            error_type="error",
            error_message="Request timed out",
            offset_seconds=1,
        )
    )

    assert len(incidents.rows) == 1
    row = incidents.rows[0]
    assert row.incident_type == "retry_storm"
    assert row.evidence.get("failure_count") == 2
    assert any(event_type == "incident.warn" for _, event_type, _ in webhook.calls)
    assert [call["event_type"] for call in transport.calls] == ["incident.warn"]


def test_loop_suspect_opens_incident_in_observe_with_warn_webhook_and_email() -> None:
    service, incidents, webhook, transport = _service(protect_enabled=False, loop_count=3)
    service.ingest(
        _event(
            "p1",
            total_tokens=42,
            feature="loop-fixed-signature",
            request_fingerprint="fp-loop-fixed",
            offset_seconds=0,
        )
    )
    service.ingest(
        _event(
            "p1",
            total_tokens=42,
            feature="loop-fixed-signature",
            request_fingerprint="fp-loop-fixed",
            offset_seconds=1,
        )
    )
    service.ingest(
        _event(
            "p1",
            total_tokens=42,
            feature="loop-fixed-signature",
            request_fingerprint="fp-loop-fixed",
            offset_seconds=2,
        )
    )

    assert len(incidents.rows) == 1
    assert incidents.rows[0].incident_type == "loop_suspect"
    warn_calls = [
        (project_id, payload) for project_id, event_type, payload in webhook.calls if event_type == "incident.warn"
    ]
    assert warn_calls
    project_id, payload = warn_calls[0]
    assert project_id == "p1"
    assert payload["provider"] == "openai"
    assert payload["requested_model"] == "gpt-4o-mini"
    assert payload["environment"] == "dev"
    evidence = payload["evidence"]
    assert isinstance(evidence, dict)
    assert evidence["signature"] == "p1:openai:gpt-4o-mini:dev:/chat/completions:loop-fixed-signature:fp-loop-fixed"
    assert evidence["request_fingerprint"] == "fp-loop-fixed"
    assert evidence["window_seconds"] == 30
    assert evidence["sequence_count"] == 3
    assert evidence["max_gap_seconds"] == 2.0
    assert evidence["threshold_count"] == 3
    assert evidence["count"] == 1
    assert "provider" not in evidence
    assert "requested_model" not in evidence
    assert "environment" not in evidence
    assert "last_seen_at" not in evidence
    assert "reason" not in evidence
    assert [call["event_type"] for call in transport.calls] == ["incident.warn"]
    assert [call["template"] for call in transport.calls] == ["incident_warn"]


def test_loop_suspect_error_sequence_does_not_trigger_on_failing_calls() -> None:
    service, incidents, webhook, transport = _service(protect_enabled=False, retry_storm_count=10, loop_count=3)
    for i in range(3):
        service.ingest(
            _event(
                "p1",
                status="error",
                http_status=500,
                error_type="provider_5xx",
                feature="loop-error-sequence",
                offset_seconds=i,
            )
        )

    assert incidents.rows == []
    assert _non_policy_gap_webhook_calls(webhook) == []
    assert transport.calls == []


def test_retry_storm_opens_without_loop_suspect_for_error_sequence() -> None:
    service, incidents, webhook, _ = _service(protect_enabled=True, retry_storm_count=3, loop_count=3)
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

    incident_types = sorted(row.incident_type for row in incidents.rows)
    assert incident_types == ["retry_storm"]
    assert sum(1 for _, event_type, _ in webhook.calls if event_type == "incident.warn") == 1


def test_loop_suspect_requires_consecutive_sequence_not_scattered_repetition() -> None:
    service, incidents, _, _ = _service(protect_enabled=False, loop_count=3)

    service.ingest(_event("p1", feature="feature-a", offset_seconds=0))
    service.ingest(_event("p1", feature="feature-a", offset_seconds=1))
    service.ingest(_event("p1", feature="feature-b", offset_seconds=2))
    service.ingest(_event("p1", feature="feature-a", offset_seconds=3))

    assert all(row.incident_type != "loop_suspect" for row in incidents.rows)


def test_loop_suspect_requires_small_gap_between_steps() -> None:
    service, incidents, webhook, transport = _service(
        protect_enabled=False,
        loop_count=3,
        loop_max_gap_seconds=1.0,
    )

    service.ingest(_event("p1", feature="gap-sequence", offset_seconds=0))
    service.ingest(_event("p1", feature="gap-sequence", offset_seconds=1))
    service.ingest(_event("p1", feature="gap-sequence", offset_seconds=4))

    assert incidents.rows == []
    assert _non_policy_gap_webhook_calls(webhook) == []
    assert transport.calls == []


def test_loop_suspect_is_suppressed_under_high_concurrency() -> None:
    service, incidents, webhook, transport = _service(
        protect_enabled=False,
        loop_count=3,
        loop_concurrency_threshold=3,
    )

    service.ingest(_event("p1", feature="loop-concurrency", offset_seconds=0))
    service.ingest(_event("p1", feature="loop-concurrency", offset_seconds=1))
    service.ingest(_event("p1", feature="loop-concurrency", offset_seconds=2))

    assert incidents.rows == []
    assert _non_policy_gap_webhook_calls(webhook) == []
    assert transport.calls == []


def test_loop_signature_is_scoped_by_feature() -> None:
    service, incidents, _, _ = _service(
        protect_enabled=False,
        loop_count=3,
        loop_concurrency_threshold=10,
    )

    service.ingest(_event("p1", feature="feature-a", offset_seconds=0))
    service.ingest(_event("p1", feature="feature-b", offset_seconds=1))
    service.ingest(_event("p1", feature="feature-a", offset_seconds=2))
    service.ingest(_event("p1", feature="feature-a", offset_seconds=3))

    assert all(row.incident_type != "loop_suspect" for row in incidents.rows)

    service.ingest(_event("p1", feature="feature-a", offset_seconds=4))

    loop_rows = [row for row in incidents.rows if row.incident_type == "loop_suspect"]
    assert len(loop_rows) == 1
    assert "feature-a" in str(loop_rows[0].evidence.get("signature"))


def test_loop_signature_is_scoped_by_request_fingerprint() -> None:
    service, incidents, webhook, transport = _service(
        protect_enabled=False,
        loop_count=3,
        loop_concurrency_threshold=10,
    )

    service.ingest(_event("p1", feature="feature-a", request_fingerprint="fp-a", offset_seconds=0))
    service.ingest(_event("p1", feature="feature-a", request_fingerprint="fp-b", offset_seconds=1))
    service.ingest(_event("p1", feature="feature-a", request_fingerprint="fp-a", offset_seconds=2))
    service.ingest(_event("p1", feature="feature-a", request_fingerprint="fp-a", offset_seconds=3))

    assert incidents.rows == []
    assert _non_policy_gap_webhook_calls(webhook) == []
    assert transport.calls == []

    service.ingest(_event("p1", feature="feature-a", request_fingerprint="fp-a", offset_seconds=4))

    loop_rows = [row for row in incidents.rows if row.incident_type == "loop_suspect"]
    assert len(loop_rows) == 1
    assert str(loop_rows[0].evidence.get("signature")).endswith(":fp-a")


def test_loop_suspect_opens_new_incident_after_episode_window_expires() -> None:
    clock, now_provider = _clock()
    service, incidents, webhook, _ = _service(
        protect_enabled=False,
        loop_count=3,
        loop_concurrency_threshold=10,
        now_provider=now_provider,
    )

    _ingest_at(
        service,
        clock,
        _event(
            "p1", total_tokens=42, feature="loop-fixed-signature", request_fingerprint="fp-loop-fixed", offset_seconds=0
        ),
    )
    _ingest_at(
        service,
        clock,
        _event(
            "p1", total_tokens=42, feature="loop-fixed-signature", request_fingerprint="fp-loop-fixed", offset_seconds=1
        ),
    )
    _ingest_at(
        service,
        clock,
        _event(
            "p1", total_tokens=42, feature="loop-fixed-signature", request_fingerprint="fp-loop-fixed", offset_seconds=2
        ),
    )
    _ingest_at(
        service,
        clock,
        _event(
            "p1",
            total_tokens=42,
            feature="loop-fixed-signature",
            request_fingerprint="fp-loop-fixed",
            offset_seconds=35,
        ),
    )
    _ingest_at(
        service,
        clock,
        _event(
            "p1",
            total_tokens=42,
            feature="loop-fixed-signature",
            request_fingerprint="fp-loop-fixed",
            offset_seconds=36,
        ),
    )
    _ingest_at(
        service,
        clock,
        _event(
            "p1",
            total_tokens=42,
            feature="loop-fixed-signature",
            request_fingerprint="fp-loop-fixed",
            offset_seconds=37,
        ),
    )

    loop_rows = [row for row in incidents.rows if row.incident_type == "loop_suspect"]
    assert len(loop_rows) == 2
    assert all(int(row.evidence.get("count", 0)) == 1 for row in loop_rows)
    warn_calls = [payload for _, event_type, payload in webhook.calls if event_type == "incident.warn"]
    assert len(warn_calls) == 2


def test_token_explosion_opens_new_incident_after_episode_window_expires() -> None:
    clock, now_provider = _clock()
    service, incidents, webhook, _ = _service(
        protect_enabled=False,
        tok_cap=None,
        token_explosion_abs=1500,
        now_provider=now_provider,
    )

    _ingest_at(service, clock, _event("p1", total_tokens=2000, feature="token-explosion-a", offset_seconds=0))
    _ingest_at(service, clock, _event("p1", total_tokens=2000, feature="token-explosion-b", offset_seconds=61))

    explosion_rows = [row for row in incidents.rows if row.incident_type == "token_explosion"]
    assert len(explosion_rows) == 2
    assert all(int(row.evidence.get("count", 0)) == 1 for row in explosion_rows)
    warn_calls = [payload for _, event_type, payload in webhook.calls if event_type == "incident.warn"]
    assert len(warn_calls) == 2


def test_token_explosion_triggers_on_growth_without_absolute_hit() -> None:
    service, incidents, webhook, transport = _service(
        protect_enabled=False,
        tok_cap=None,
        token_explosion_abs=10_000,
        token_explosion_growth_ratio=1.7,
        token_explosion_growth_count=2,
        token_explosion_growth_min_tokens=1_800,
    )

    service.ingest(_event("p1", total_tokens=1_900, feature="growth-seed", offset_seconds=0))
    service.ingest(_event("p1", total_tokens=3_230, feature="growth-seed", offset_seconds=1))
    assert incidents.rows == []

    service.ingest(_event("p1", total_tokens=5_500, feature="growth-seed", offset_seconds=2))

    assert len(incidents.rows) == 1
    row = incidents.rows[0]
    assert row.incident_type == "token_explosion"
    assert row.evidence.get("previous_token_explosion_tokens") == 3_230
    assert row.evidence.get("growth_hit") is True
    assert row.evidence.get("growth_threshold") == 1.7
    assert row.evidence.get("growth_required_count") == 2
    assert row.evidence.get("growth_sequence_count") == 2
    assert row.evidence.get("growth_min_tokens") == 1_800
    assert row.evidence.get("absolute_hit") is False
    assert "ratio_hit" not in row.evidence
    assert "ratio_threshold_tokens" not in row.evidence
    assert webhook.calls
    assert [call["event_type"] for call in transport.calls] == ["incident.warn"]
    assert [call["template"] for call in transport.calls] == ["incident_warn"]


def test_token_explosion_growth_ignores_tiny_request_context_jumps() -> None:
    service, incidents, webhook, transport = _service(
        protect_enabled=False,
        tok_cap=None,
        token_explosion_abs=10_000,
        token_explosion_growth_ratio=1.7,
        token_explosion_growth_count=2,
        token_explosion_growth_min_tokens=1_800,
    )

    service.ingest(_event("p1", total_tokens=120, feature="growth-noise", offset_seconds=0))
    service.ingest(_event("p1", total_tokens=363, feature="growth-noise", offset_seconds=1))

    assert incidents.rows == []
    assert _non_policy_gap_webhook_calls(webhook) == []
    assert transport.calls == []


def test_token_explosion_uses_dedicated_request_context_signal_on_ingest() -> None:
    service, incidents, webhook, transport = _service(
        protect_enabled=False,
        req_cap=None,
        tok_cap=None,
        token_explosion_abs=200,
    )

    service.ingest(_event("p1", total_tokens=50, token_explosion_tokens=240, feature="context-growth"))

    assert len(incidents.rows) == 1
    row = incidents.rows[0]
    assert row.incident_type == "token_explosion"
    assert row.evidence.get("token_explosion_tokens") == 240
    assert row.evidence.get("absolute_hit") is True
    assert "ratio_hit" not in row.evidence
    assert "ratio_threshold_tokens" not in row.evidence
    assert webhook.calls
    assert [call["event_type"] for call in transport.calls] == ["incident.warn"]
    assert [call["template"] for call in transport.calls] == ["incident_warn"]


def test_token_explosion_growth_is_suppressed_under_high_concurrency() -> None:
    service, incidents, webhook, transport = _service(
        protect_enabled=False,
        tok_cap=None,
        token_explosion_abs=10_000,
        token_explosion_growth_ratio=1.7,
        token_explosion_growth_count=2,
        token_explosion_growth_min_tokens=1_800,
        token_explosion_concurrency_threshold=2,
    )

    service.ingest(_event("p1", total_tokens=1_900, feature="growth-concurrency", offset_seconds=0))
    service.ingest(_event("p1", total_tokens=3_230, feature="growth-concurrency", offset_seconds=1))
    service.ingest(_event("p1", total_tokens=5_500, feature="growth-concurrency", offset_seconds=2))

    assert incidents.rows == []
    assert _non_policy_gap_webhook_calls(webhook) == []
    assert transport.calls == []


def test_token_explosion_growth_ignores_unrelated_feature_history() -> None:
    service, incidents, webhook, transport = _service(
        protect_enabled=False,
        tok_cap=None,
        token_explosion_abs=10_000,
        token_explosion_growth_ratio=1.7,
        token_explosion_growth_count=2,
        token_explosion_growth_min_tokens=1_800,
    )

    service.ingest(_event("p1", total_tokens=9_000, feature="other-feature", offset_seconds=0))
    service.ingest(_event("p1", total_tokens=1_900, feature="token-explosion-growth", offset_seconds=1))
    service.ingest(_event("p1", total_tokens=3_230, feature="token-explosion-growth", offset_seconds=2))
    service.ingest(_event("p1", total_tokens=5_500, feature="token-explosion-growth", offset_seconds=3))

    assert len(incidents.rows) == 1
    row = incidents.rows[0]
    assert row.incident_type == "token_explosion"
    assert row.evidence.get("previous_token_explosion_tokens") == 3_230
    assert webhook.calls
    assert [call["event_type"] for call in transport.calls] == ["incident.warn"]
    assert [call["template"] for call in transport.calls] == ["incident_warn"]


def test_token_explosion_incident_emits_warn_in_protect_mode() -> None:
    service, incidents, webhook, _ = _service(protect_enabled=True, tok_cap=10_000, token_explosion_abs=1500)
    service.ingest(_event("p1", total_tokens=1800, offset_seconds=0))

    assert len(incidents.rows) == 1
    assert incidents.rows[0].incident_type == "token_explosion"
    assert any(event_type == "incident.warn" for _, event_type, _ in webhook.calls)


def test_token_explosion_growth_does_not_also_open_loop_suspect() -> None:
    service, incidents, webhook, transport = _service(
        protect_enabled=True,
        req_cap=None,
        tok_cap=None,
        loop_count=1,
        token_explosion_abs=10_000,
        token_explosion_growth_ratio=1.7,
        token_explosion_growth_count=2,
        token_explosion_growth_min_tokens=1_800,
    )

    service.ingest(_event("p1", total_tokens=1_900, feature="token-loop-overlap", offset_seconds=0))
    service.ingest(_event("p1", total_tokens=3_230, feature="token-loop-overlap", offset_seconds=1))
    service.ingest(_event("p1", total_tokens=5_500, feature="token-loop-overlap", offset_seconds=2))

    incident_types = sorted(row.incident_type for row in incidents.rows)
    assert incident_types == ["token_explosion"]
    assert [call["event_type"] for call in transport.calls] == ["incident.warn"]
    assert all(event_type == "incident.warn" for _, event_type, _ in webhook.calls)


def test_token_explosion_absolute_hit_does_not_depend_on_tok_cap_or_open_loop_suspect() -> None:
    service, incidents, webhook, transport = _service(
        protect_enabled=True,
        req_cap=None,
        tok_cap=20_000,
        loop_count=1,
        token_explosion_abs=1_500,
    )

    service.ingest(_event("p1", total_tokens=1_800, feature="token-loop-absolute", offset_seconds=0))

    incident_types = sorted(row.incident_type for row in incidents.rows)
    assert incident_types == ["token_explosion"]
    assert incidents.rows[0].evidence.get("absolute_hit") is True
    assert "ratio_hit" not in incidents.rows[0].evidence
    assert "ratio_threshold_tokens" not in incidents.rows[0].evidence
    assert [call["event_type"] for call in transport.calls] == ["incident.warn"]
    assert all(event_type == "incident.warn" for _, event_type, _ in webhook.calls)


def test_behavioral_retry_and_loop_suspect_can_coexist() -> None:
    service, incidents, _, _ = _service(
        protect_enabled=True, req_cap=None, tok_cap=None, retry_storm_count=1, loop_count=1
    )
    service.ingest(
        _event(
            "p1",
            total_tokens=60,
            status="error",
            http_status=500,
            error_type="provider_5xx",
            feature="dominance-retry-loop",
            offset_seconds=0,
        )
    )
    service.ingest(_event("p1", total_tokens=60, feature="dominance-retry-loop", offset_seconds=1))

    incident_types = sorted({row.incident_type for row in incidents.rows})
    assert incident_types == ["loop_suspect", "retry_storm"]


def test_behavioral_retry_and_token_explosion_can_coexist_without_caps() -> None:
    service, incidents, _, _ = _service(
        protect_enabled=True, req_cap=None, tok_cap=None, retry_storm_count=1, token_explosion_abs=1500
    )
    service.ingest(
        _event(
            "p1",
            total_tokens=1800,
            status="error",
            http_status=500,
            error_type="provider_5xx",
            feature="dominance-token-retry",
            offset_seconds=0,
        )
    )

    incident_types = sorted(row.incident_type for row in incidents.rows)
    assert incident_types == ["retry_storm", "token_explosion"]


def test_active_block_incident_suppresses_token_explosion_in_same_window() -> None:
    service, incidents, webhook, transport = _service(
        protect_enabled=True,
        req_cap=None,
        tok_cap=None,
        token_explosion_abs=1500,
    )
    now = datetime.now(timezone.utc)
    incidents.rows.append(
        Incident(
            id="inc-block-1",
            project_id="p1",
            provider="openai",
            incident_type="block",
            status="open",
            created_at=now - timedelta(seconds=30),
            resolved_at=None,
            evidence={"reason": "req_cap_breach", "count": 1},
            fingerprint="p1:openai:block:req_cap_breach",
            last_seen_at=now - timedelta(seconds=5),
        )
    )

    service.ingest(_event("p1", total_tokens=1800, feature="blocked-token-explosion", offset_seconds=0))

    incident_types = sorted(row.incident_type for row in incidents.rows)
    assert incident_types == ["block"]
    assert _non_policy_gap_webhook_calls(webhook) == []
    assert transport.calls == []


def test_active_block_incident_suppresses_retry_and_loop_in_same_window() -> None:
    service, incidents, webhook, transport = _service(
        protect_enabled=True,
        req_cap=None,
        tok_cap=None,
        retry_storm_count=1,
        loop_count=1,
    )
    now = datetime.now(timezone.utc)
    incidents.rows.append(
        Incident(
            id="inc-block-2",
            project_id="p1",
            provider="openai",
            incident_type="block",
            status="open",
            created_at=now - timedelta(seconds=30),
            resolved_at=None,
            evidence={"reason": "tok_cap_breach", "count": 1},
            fingerprint="p1:openai:block:tok_cap_breach",
            last_seen_at=now - timedelta(seconds=5),
        )
    )

    service.ingest(
        _event(
            "p1",
            total_tokens=60,
            status="error",
            http_status=500,
            error_type="provider_5xx",
            feature="blocked-retry-loop",
            offset_seconds=0,
        )
    )
    service.ingest(_event("p1", total_tokens=60, feature="blocked-retry-loop", offset_seconds=1))

    incident_types = sorted(row.incident_type for row in incidents.rows)
    assert incident_types == ["block"]
    assert _non_policy_gap_webhook_calls(webhook) == []
    assert transport.calls == []


def test_policy_gap_first_seen_baseline_sends_no_webhook_and_no_incident() -> None:
    service, incidents, webhook, _ = _service(protect_enabled=True)
    service.ingest(_event("p1", provider="openai", requested_model="gpt-4o-mini", total_tokens=10, offset_seconds=0))
    service.ingest(_event("p1", provider="openai", requested_model="gpt-4o-mini", total_tokens=12, offset_seconds=30))

    policy_gap_calls = [call for call in webhook.calls if call[1] == "policy_gap.detected"]
    assert len(policy_gap_calls) == 0
    assert incidents.rows == []


def test_policy_gap_webhook_is_sent_only_after_project_has_baseline_history() -> None:
    service, incidents, webhook, _ = _service(protect_enabled=False)
    service.ingest(_event("p1", provider="openai", requested_model="gpt-4o-mini", total_tokens=10, offset_seconds=0))
    service.ingest(
        _event("p1", provider="google", requested_model="gemini-1.5-pro", total_tokens=12, offset_seconds=30)
    )

    assert any(event_type == "policy_gap.detected" for _, event_type, _ in webhook.calls)
    assert incidents.rows == []
