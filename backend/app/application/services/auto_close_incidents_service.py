# Application service for incident auto-close by cooldown.
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.application.interfaces.incident_repository import IncidentRepository
from app.domain.models.incident import Incident
from app.infrastructure.redis.incident_severity_cache import IncidentSeverityCache
from app.logger import get_logger

logger = get_logger(__name__)


class AutoCloseIncidentsService:
    # Auto-resolves stale open incidents and refreshes incident severity cache.

    def __init__(
        self,
        incident_repository: IncidentRepository,
        incident_severity_cache: IncidentSeverityCache | None,
        cooldown_seconds: int,
    ) -> None:
        self._incident_repository = incident_repository
        self._incident_severity_cache = incident_severity_cache
        self._cooldown_seconds = max(int(cooldown_seconds), 1)

    def auto_close(self, now: datetime | None = None) -> int:
        # Resolve stale incidents and return number of rows changed.
        resolved_at = now or datetime.now(timezone.utc)
        cutoff = resolved_at - timedelta(seconds=self._cooldown_seconds)
        resolved_count, affected_projects = self._incident_repository.auto_resolve_stale_open_incidents(
            cutoff=cutoff,
            resolved_at=resolved_at,
        )
        if self._incident_severity_cache is not None:
            for project_id in affected_projects:
                open_incidents = self._incident_repository.list_by_project(project_id=project_id, status="open")
                self._incident_severity_cache.set(project_id=project_id, severity=_highest_severity(open_incidents))
        return resolved_count


def _highest_severity(incidents: list[Incident]) -> str:
    # Return highest severity across currently open incidents.
    ranking = {"none": 0, "low": 1, "medium": 2, "high": 3}
    highest = "none"
    for incident in incidents:
        if ranking.get(incident.severity, 0) > ranking.get(highest, 0):
            highest = incident.severity
    return highest
