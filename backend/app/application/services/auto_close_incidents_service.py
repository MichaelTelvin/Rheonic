# Application service for incident auto-close by cooldown.
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.application.interfaces.incident_repository import IncidentRepository
from app.application.interfaces.project_repository import ProjectRepository
from app.application.services.transport_service import TransportService, build_transport_dedupe_key
from app.application.interfaces.webhook_dispatcher import WebhookDispatcher
from app.domain.models.incident import Incident
from app.logger import get_logger

logger = get_logger(__name__)


class AutoCloseIncidentsService:
    # Auto-resolves stale open incidents.

    def __init__(
        self,
        incident_repository: IncidentRepository,
        cooldown_seconds: int,
        webhook_dispatcher: WebhookDispatcher | None = None,
        transport_service: TransportService | None = None,
        project_repository: ProjectRepository | None = None,
    ) -> None:
        self._incident_repository = incident_repository
        self._cooldown_seconds = max(int(cooldown_seconds), 1)
        self._webhook_dispatcher = webhook_dispatcher
        self._transport_service = transport_service
        self._project_repository = project_repository

    def auto_close(self, now: datetime | None = None) -> int:
        # Resolve stale incidents and return number of rows changed.
        resolved_at = now or datetime.now(timezone.utc)
        cutoff = resolved_at - timedelta(seconds=self._cooldown_seconds)
        resolved_incidents, affected_pairs = self._incident_repository.auto_resolve_stale_open_incidents(
            cutoff=cutoff,
            resolved_at=resolved_at,
        )
        _ = affected_pairs
        for incident in resolved_incidents:
            self._enqueue_incident_resolved_notifications(incident=incident, resolved_by="auto")
        return len(resolved_incidents)

    def _enqueue_incident_resolved_notifications(self, *, incident: Incident, resolved_by: str) -> None:
        # Auto-resolve uses the same protect lifecycle transport fan-out as manual resolve.
        if not self._is_protect_mode_enabled(incident.project_id):
            return
        provider, model, environment = _incident_dimensions(incident)
        resolved_at = incident.resolved_at or datetime.now(timezone.utc)
        payload = {
            "event": "incident.resolved",
            "project_id": incident.project_id,
            "incident_id": incident.id,
            "incident_type": incident.incident_type,
            "resolved_by": resolved_by,
            "resolved_at": resolved_at.isoformat(),
            "created_at": incident.created_at.isoformat(),
            "last_seen_at": incident.last_seen_at.isoformat() if incident.last_seen_at is not None else None,
            "provider": provider,
            "model": model,
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
                logger.exception("Failed to enqueue auto incident resolved webhook", extra={"incident_id": incident.id})
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
            logger.exception("Failed to enqueue auto incident resolved email", extra={"incident_id": incident.id})

    def _is_protect_mode_enabled(self, project_id: str) -> bool:
        if self._project_repository is None:
            return False
        project = self._project_repository.get_project(project_id)
        return bool(project is not None and project.protect_enabled)


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
