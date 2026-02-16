# Incident resolve endpoint tests.
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.application.services.detect_incidents_service import DetectIncidentsService
from app.dependencies import get_detect_incidents_service
from app.domain.models.incident import Incident
from app.main import app
from app.infrastructure.redis.rolling_window import incident_open_lock_key


class FakeIncidentRepository:
    # In-memory incident repository used by route test.
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.incident = Incident(
            id="inc-1",
            project_id="p1",
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

    def resolve_incident(self, incident_id: str) -> Incident | None:
        if incident_id != self.incident.id:
            return None
        self.incident.status = "resolved"
        self.incident.resolved_at = datetime.now(timezone.utc)
        return self.incident


class FakeRealtimeStore:
    # In-memory lock store used by route test.
    def __init__(self) -> None:
        self.locks: set[str] = {incident_open_lock_key("p1", "burn_spike")}

    def release_incident_lock(self, project_id: str, incident_type: str) -> None:
        key = incident_open_lock_key(project_id, incident_type)
        self.locks.discard(key)


def test_resolve_endpoint_marks_resolved_and_deletes_lock() -> None:
    # Resolve endpoint should update incident status and remove dedupe key.
    repo = FakeIncidentRepository()
    realtime = FakeRealtimeStore()
    service = DetectIncidentsService(
        incident_repository=repo,  # type: ignore[arg-type]
        realtime_counters=realtime,  # type: ignore[arg-type]
    )

    app.dependency_overrides[get_detect_incidents_service] = lambda: service
    client = TestClient(app)

    response = client.post("/api/v1/incidents/inc-1/resolve")

    assert response.status_code == 200
    assert response.json() == {"status": "resolved"}
    assert incident_open_lock_key("p1", "burn_spike") not in realtime.locks

    app.dependency_overrides.clear()
