# Application service for incident auto-close by cooldown.
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.application.interfaces.incident_repository import IncidentRepository
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
    ) -> None:
        self._incident_repository = incident_repository
        self._cooldown_seconds = max(int(cooldown_seconds), 1)
        self._webhook_dispatcher = webhook_dispatcher

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
            self._enqueue_incident_resolved_webhook(incident=incident, resolved_by="auto")
        return len(resolved_incidents)

    def _enqueue_incident_resolved_webhook(self, *, incident: Incident, resolved_by: str) -> None:
        # Enqueue webhook for auto-resolved incidents.
        if self._webhook_dispatcher is None:
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
        try:
            self._webhook_dispatcher.enqueue(
                project_id=incident.project_id,
                payload=payload,
                event_type="incident.resolved",
            )
        except Exception:
            logger.exception("Failed to enqueue auto incident resolved webhook", extra={"incident_id": incident.id})


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
