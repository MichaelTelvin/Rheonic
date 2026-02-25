# Application service for incident detection.
from datetime import datetime, timezone

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.interfaces.incident_repository import IncidentRepository
from app.application.provider_scope import scoped_project_provider_id
from app.application.interfaces.webhook_dispatcher import WebhookDispatcher
from app.domain.models.incident import Incident
from app.infrastructure.redis.incident_severity_cache import IncidentSeverityCache
from app.logger import get_logger

logger = get_logger(__name__)


class DetectIncidentsService:
    # Runs configured detectors over event streams.

    def __init__(
        self,
        incident_repository: IncidentRepository,
        realtime_counters: RealtimeCounterStore,
        incident_severity_cache: IncidentSeverityCache | None = None,
        webhook_dispatcher: WebhookDispatcher | None = None,
    ) -> None:
        # Initialize dependencies.
        self._incident_repository = incident_repository
        self._realtime_counters = realtime_counters
        self._incident_severity_cache = incident_severity_cache
        self._webhook_dispatcher = webhook_dispatcher

    def detect(self) -> list[object]:
        # Detect incidents and return incident DTOs.
        try:
            # TODO: Run domain detectors and persist incidents.
            logger.debug("Detect incidents service called")
            return []
        except Exception:
            logger.exception("Detect incidents service failed")
            raise

    def list_incidents(self, project_id: str, status: str = "open", provider: str | None = None) -> list[Incident]:
        # List incidents for project and status.
        try:
            return self._incident_repository.list_by_project(project_id=project_id, status=status, provider=provider)
        except Exception:
            logger.exception(
                "List incidents service failed",
                extra={"project_id": project_id, "status": status, "provider": provider},
            )
            raise

    def get_incident(self, incident_id: str) -> Incident | None:
        # Fetch an incident by id.
        try:
            return self._incident_repository.get_by_id(incident_id=incident_id)
        except Exception:
            logger.exception("Get incident service failed", extra={"incident_id": incident_id})
            raise

    def resolve_incident(self, incident_id: str) -> Incident | None:
        # Resolve incident and release dedupe lock.
        try:
            incident = self._incident_repository.resolve_incident(incident_id=incident_id)
            if incident is None:
                return None
            self._realtime_counters.release_incident_lock(
                project_id=scoped_project_provider_id(incident.project_id, incident.provider),
                incident_type=incident.incident_type,
            )
            if self._incident_severity_cache is not None:
                open_incidents = self._incident_repository.list_open_by_project_provider(
                    project_id=incident.project_id,
                    provider=incident.provider,
                )
                self._incident_severity_cache.set(
                    project_id=scoped_project_provider_id(incident.project_id, incident.provider),
                    severity=_highest_severity(open_incidents),
                )
            self._enqueue_incident_resolved_webhook(incident=incident, resolved_by="manual")
            return incident
        except Exception:
            logger.exception("Resolve incident service failed", extra={"incident_id": incident_id})
            raise

    def _enqueue_incident_resolved_webhook(self, *, incident: Incident, resolved_by: str) -> None:
        # Enqueue webhook for incident resolution state changes.
        if self._webhook_dispatcher is None:
            return
        provider, model, environment = _incident_dimensions(incident)
        resolved_at = incident.resolved_at or datetime.now(timezone.utc)
        payload = {
            "event": "incident.resolved",
            "project_id": incident.project_id,
            "incident_id": incident.id,
            "incident_type": incident.incident_type,
            "severity": incident.severity,
            "resolved_by": resolved_by,
            "resolved_at": resolved_at.isoformat(),
            "created_at": incident.created_at.isoformat(),
            "last_seen_at": incident.last_seen_at.isoformat() if incident.last_seen_at is not None else None,
            "provider": provider,
            "model": model,
            "environment": environment,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._webhook_dispatcher.enqueue(
                project_id=incident.project_id,
                payload=payload,
                event_type="incident.resolved",
            )
        except Exception:
            logger.exception("Failed to enqueue manual incident resolved webhook", extra={"incident_id": incident.id})


def _highest_severity(incidents: list[Incident]) -> str:
    # Return highest open incident severity for cache refresh.
    ranking = {"none": 0, "low": 1, "medium": 2, "high": 3}
    highest = "none"
    for incident in incidents:
        if ranking.get(incident.severity, 0) > ranking.get(highest, 0):
            highest = incident.severity
    return highest


def _incident_dimensions(incident: Incident) -> tuple[str | None, str | None, str | None]:
    # Extract provider/model/environment from incident evidence when present.
    evidence = incident.evidence or {}
    provider = incident.provider or evidence.get("provider")
    model = evidence.get("model")
    environment = evidence.get("environment")
    return (
        str(provider) if isinstance(provider, str) else None,
        str(model) if isinstance(model, str) else None,
        str(environment) if isinstance(environment, str) else None,
    )
