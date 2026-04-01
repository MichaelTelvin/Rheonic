# Application service for incident detection.
from datetime import datetime, timezone

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.interfaces.incident_repository import IncidentRepository
from app.application.interfaces.project_repository import ProjectRepository
from app.application.interfaces.webhook_dispatcher import WebhookDispatcher
from app.application.provider_scope import scoped_project_provider_id
from app.application.services.transport_service import TransportService, build_transport_dedupe_key
from app.domain.models.incident import Incident
from app.logger import get_logger

logger = get_logger(__name__)


class DetectIncidentsService:
    # Runs configured detectors over event streams.

    def __init__(
        self,
        incident_repository: IncidentRepository,
        realtime_counters: RealtimeCounterStore,
        webhook_dispatcher: WebhookDispatcher | None = None,
        transport_service: TransportService | None = None,
        project_repository: ProjectRepository | None = None,
    ) -> None:
        # Initialize dependencies.
        self._incident_repository = incident_repository
        self._realtime_counters = realtime_counters
        self._webhook_dispatcher = webhook_dispatcher
        self._transport_service = transport_service
        self._project_repository = project_repository

    def list_incidents(
        self,
        project_id: str,
        status: str = "open",
        provider: str | None = None,
    ) -> list[Incident]:
        # List incidents for project and status.
        try:
            return self._incident_repository.list_by_project(
                project_id=project_id,
                status=status,
                provider=provider,
            )
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
            self._enqueue_incident_resolved_notifications(incident=incident, resolved_by="manual")
            return incident
        except Exception:
            logger.exception("Resolve incident service failed", extra={"incident_id": incident_id})
            raise

    def _enqueue_incident_resolved_notifications(self, *, incident: Incident, resolved_by: str) -> None:
        # Resolution webhooks are part of the raw incident lifecycle in both modes.
        # Email remains protect-only.
        provider, requested_model, environment = _incident_dimensions(incident)
        resolved_at = incident.resolved_at or datetime.now(timezone.utc)
        payload: dict[str, object] = {
            "event": "incident.resolved",
            "project_id": incident.project_id,
            "incident_id": incident.id,
            "incident_type": incident.incident_type,
            "resolved_by": resolved_by,
            "resolved_at": resolved_at.isoformat(),
            "created_at": incident.created_at.isoformat(),
            "last_seen_at": incident.last_seen_at.isoformat() if incident.last_seen_at is not None else None,
            "provider": provider,
            "requested_model": requested_model,
            "resolved_model": _incident_resolved_model(incident),
            "environment": environment,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        if self._webhook_dispatcher is not None:
            try:
                self._webhook_dispatcher.enqueue(
                    project_id=incident.project_id,
                    payload=payload,
                    event_type="incident.resolved",
                )
            except Exception:
                logger.exception(
                    "Failed to enqueue manual incident resolved webhook", extra={"incident_id": incident.id}
                )
        if not self._is_protect_mode_enabled(incident.project_id):
            return
        if self._transport_service is None:
            return
        try:
            dedupe_key = build_transport_dedupe_key(
                project_id=incident.project_id,
                kind="email",
                event_type="incident.resolved",
                payload=payload,
                seed=incident.id,
            )
            self._transport_service.enqueue(
                project_id=incident.project_id,
                kind="email",
                event_type="incident.resolved",
                payload=payload,
                dedupe_key=dedupe_key,
                template="incident_resolved",
                provider=provider,
                environment=environment,
            )
        except Exception:
            logger.exception("Failed to enqueue manual incident resolved email", extra={"incident_id": incident.id})

    def _is_protect_mode_enabled(self, project_id: str) -> bool:
        if self._project_repository is None:
            return False
        project = self._project_repository.get_project(project_id)
        return bool(project is not None and project.protect_enabled)


def _incident_dimensions(incident: Incident) -> tuple[str | None, str | None, str | None]:
    # Extract provider/requested_model/environment from incident evidence when present.
    evidence = incident.evidence or {}
    provider = incident.provider or evidence.get("provider")
    requested_model = evidence.get("requested_model")
    environment = evidence.get("environment")
    return (
        str(provider) if isinstance(provider, str) else None,
        str(requested_model) if isinstance(requested_model, str) else None,
        str(environment) if isinstance(environment, str) else None,
    )


def _incident_resolved_model(incident: Incident) -> str | None:
    evidence = incident.evidence or {}
    resolved_model = evidence.get("resolved_model")
    return str(resolved_model) if isinstance(resolved_model, str) else None
