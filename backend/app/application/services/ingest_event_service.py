# Application service for event ingestion.
from datetime import datetime, timezone
from uuid import uuid4

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.interfaces.event_repository import EventRepository
from app.application.interfaces.incident_repository import IncidentRepository
from app.domain.models.incident import Incident
from app.domain.models.event import Event
from app.logger import get_logger

logger = get_logger(__name__)


class IngestEventService:
    # Orchestrates ingest flow without transport or persistence details.

    def __init__(
        self,
        event_repository: EventRepository,
        realtime_counters: RealtimeCounterStore,
        incident_repository: IncidentRepository,
        threshold_tokens_60s: int,
        threshold_req_60s: int,
        incident_lock_ttl_seconds: int,
    ) -> None:
        # Initialize service dependencies.
        self._event_repository = event_repository
        self._realtime_counters = realtime_counters
        self._incident_repository = incident_repository
        self._threshold_tokens_60s = threshold_tokens_60s
        self._threshold_req_60s = threshold_req_60s
        self._incident_lock_ttl_seconds = incident_lock_ttl_seconds

    def ingest(self, event: Event) -> None:
        # Persist a single event and update realtime counters.
        try:
            # persist event to durable store
            self._event_repository.add(event)

            # update realtime 60s counters
            self._realtime_counters.increment_project_60s(
                project_id=event.project_id,
                total_tokens=event.total_tokens,
            )
            requests_60s, tokens_60s = self._realtime_counters.get_project_60s(project_id=event.project_id)
            self._create_incidents_if_needed(event=event, requests_60s=requests_60s, tokens_60s=tokens_60s)
            logger.info("Event ingested", extra={"project_id": event.project_id, "event_id": event.id})
        except Exception:
            logger.exception("Ingest service failed", extra={"project_id": event.project_id})
            raise

    def _create_incidents_if_needed(self, event: Event, requests_60s: int, tokens_60s: int) -> None:
        # Evaluate simple threshold rules and create deduped incidents.
        now = datetime.now(timezone.utc)
        rules = [
            ("burn_spike", tokens_60s, self._threshold_tokens_60s),
            ("request_storm", requests_60s, self._threshold_req_60s),
        ]
        for incident_type, value, threshold in rules:
            if value < threshold:
                continue
            severity = _severity_for_value(value=value, threshold=threshold)
            lock_acquired = self._realtime_counters.acquire_incident_lock(
                project_id=event.project_id,
                incident_type=incident_type,
                ttl_seconds=self._incident_lock_ttl_seconds,
            )
            if not lock_acquired:
                logger.debug(
                    "Incident deduped by lock",
                    extra={"project_id": event.project_id, "incident_type": incident_type},
                )
                continue
            incident = Incident(
                id=str(uuid4()),
                project_id=event.project_id,
                incident_type=incident_type,
                severity=severity,
                status="open",
                created_at=now,
                resolved_at=None,
                evidence={
                    "requests_60s": requests_60s,
                    "tokens_60s": tokens_60s,
                    "threshold_req_60s": self._threshold_req_60s,
                    "threshold_tokens_60s": self._threshold_tokens_60s,
                    "provider": event.provider,
                    "model": event.model,
                    "timestamp": now.isoformat(),
                },
            )
            self._incident_repository.create_incident(incident=incident)
            logger.info(
                "Incident created from ingest",
                extra={"project_id": event.project_id, "incident_type": incident_type, "severity": severity},
            )


def _severity_for_value(value: int, threshold: int) -> str:
    # Map threshold breach multipliers to incident severity.
    if value >= threshold * 4:
        return "high"
    if value >= threshold * 2:
        return "medium"
    return "low"
