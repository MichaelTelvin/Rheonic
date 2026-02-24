# Incident resolve endpoint tests.
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.application.services.detect_incidents_service import DetectIncidentsService
from app.application.provider_scope import scoped_project_provider_id
from fastapi import HTTPException

from app.dependencies import get_current_user, get_detect_incidents_service, get_project_service
from app.domain.models.incident import Incident
from app.domain.models.project import Project
from app.domain.models.user import User
from app.main import app
from app.infrastructure.redis.rolling_window import incident_open_lock_key


class FakeIncidentRepository:
    # In-memory incident repository used by route test.
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.incident = Incident(
            id="inc-1",
            project_id="p1",
            provider="openai",
            incident_type="burn_spike",
            severity="low",
            status="open",
            created_at=now,
            resolved_at=None,
            evidence={"requests_60s": 1, "tokens_60s": 10},
        )

    def list_by_project(self, project_id: str, status: str = "open") -> list[Incident]:
        if self.incident.project_id == project_id and self.incident.status == status:
            return [self.incident]
        return []

    def get_by_id(self, incident_id: str) -> Incident | None:
        if incident_id == self.incident.id:
            return self.incident
        return None

    def resolve_incident(self, incident_id: str) -> Incident | None:
        if incident_id != self.incident.id:
            return None
        self.incident.status = "resolved"
        self.incident.resolved_at = datetime.now(timezone.utc)
        return self.incident


class FakeRealtimeStore:
    # In-memory lock store used by route test.
    def __init__(self) -> None:
        self.locks: set[str] = {incident_open_lock_key(scoped_project_provider_id("p1", "openai"), "burn_spike")}

    def release_incident_lock(self, project_id: str, incident_type: str) -> None:
        key = incident_open_lock_key(project_id, incident_type)
        self.locks.discard(key)


class FakeWebhookDispatcher:
    # Captures webhook dispatch enqueue calls.
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


class FakeProjectService:
    # Minimal ownership verifier for resolve endpoint tests.
    def ensure_project_owned_by_user(self, project_id: str, user_id: str) -> Project:
        if project_id != "p1" or user_id != "u1":
            raise HTTPException(status_code=404, detail="project not found")
        return Project(
            id="p1",
            name="Demo",
            user_id="u1",
            created_at=datetime.now(timezone.utc),
        )


def test_resolve_endpoint_marks_resolved_and_deletes_lock() -> None:
    # Resolve endpoint should update incident status and remove dedupe key.
    repo = FakeIncidentRepository()
    realtime = FakeRealtimeStore()
    dispatcher = FakeWebhookDispatcher()
    service = DetectIncidentsService(
        incident_repository=repo,  # type: ignore[arg-type]
        realtime_counters=realtime,  # type: ignore[arg-type]
        webhook_dispatcher=dispatcher,  # type: ignore[arg-type]
    )

    app.dependency_overrides[get_detect_incidents_service] = lambda: service
    app.dependency_overrides[get_project_service] = lambda: FakeProjectService()
    app.dependency_overrides[get_current_user] = lambda: User(
        id="u1",
        email="u1@example.com",
        password_hash="hashed",
        created_at=datetime.now(timezone.utc),
    )
    client = TestClient(app)

    response = client.post("/api/v1/incidents/inc-1/resolve")

    assert response.status_code == 200
    assert response.json() == {"status": "resolved"}
    assert incident_open_lock_key(scoped_project_provider_id("p1", "openai"), "burn_spike") not in realtime.locks
    assert len(dispatcher.calls) == 1
    _, payload, event_type = dispatcher.calls[0]
    assert event_type == "incident.resolved"
    assert payload["event"] == "incident.resolved"
    assert payload["resolved_by"] == "manual"
    assert payload["incident_id"] == "inc-1"

    app.dependency_overrides.clear()
