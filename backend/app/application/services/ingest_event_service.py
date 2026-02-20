# Application service for event ingestion.
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.interfaces.event_repository import EventRepository
from app.application.interfaces.incident_repository import IncidentRepository
from app.infrastructure.redis.incident_severity_cache import IncidentSeverityCache
from app.domain.models.incident import Incident
from app.domain.models.event import Event
from app.logger import get_logger

logger = get_logger(__name__)

INCIDENT_TYPE_BURN_SPIKE = "burn_spike"
INCIDENT_TYPE_REQUEST_SPIKE = "request_spike"
LOW_SEVERITY_RATIO = 2.0
MEDIUM_SEVERITY_RATIO = 5.0
HIGH_SEVERITY_RATIO = 10.0


class IngestEventService:
    # Orchestrates ingest flow without transport or persistence details.

    def __init__(
        self,
        event_repository: EventRepository,
        realtime_counters: RealtimeCounterStore,
        incident_repository: IncidentRepository,
        incident_severity_cache: IncidentSeverityCache | None,
        baseline_window_count: int,
        incident_dedup_window_seconds: int,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        # Initialize service dependencies.
        self._event_repository = event_repository
        self._realtime_counters = realtime_counters
        self._incident_repository = incident_repository
        self._incident_severity_cache = incident_severity_cache
        self._baseline_window_count = baseline_window_count
        self._incident_dedup_window_seconds = incident_dedup_window_seconds
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

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
            try:
                if self._has_open_incident_for_dimension(event=event):
                    baseline_req_60s, baseline_tok_60s = self._realtime_counters.get_baseline_snapshot(
                        project_id=event.project_id,
                        max_windows=self._baseline_window_count,
                    )
                else:
                    baseline_req_60s, baseline_tok_60s = self._realtime_counters.record_baseline_snapshot(
                        project_id=event.project_id,
                        requests_60s=requests_60s,
                        tokens_60s=tokens_60s,
                        max_windows=self._baseline_window_count,
                    )
                self._create_incident_if_needed(
                    event=event,
                    requests_60s=requests_60s,
                    tokens_60s=tokens_60s,
                    baseline_req_60s=baseline_req_60s,
                    baseline_tok_60s=baseline_tok_60s,
                )
            except Exception:
                logger.exception("Anomaly evaluation failed during ingest", extra={"project_id": event.project_id})
            logger.info("Event ingested", extra={"project_id": event.project_id, "event_id": event.id})
        except Exception:
            logger.exception("Ingest service failed", extra={"project_id": event.project_id})
            raise

    def _has_open_incident_for_dimension(self, event: Event) -> bool:
        # Freeze baseline updates while any open anomaly incident exists for this event dimension.
        created_after = datetime.fromtimestamp(0, tz=timezone.utc)
        for incident_type in (INCIDENT_TYPE_BURN_SPIKE, INCIDENT_TYPE_REQUEST_SPIKE):
            fingerprint = _build_incident_fingerprint(
                project_id=event.project_id,
                incident_type=incident_type,
                provider=event.provider,
                model=event.model,
                environment=event.environment,
            )
            open_incident = self._incident_repository.get_open_incident_by_fingerprint(
                project_id=event.project_id,
                fingerprint=fingerprint,
                created_after=created_after,
            )
            if open_incident is not None:
                return True
        return False

    def _create_incident_if_needed(
        self,
        event: Event,
        requests_60s: int,
        tokens_60s: int,
        baseline_req_60s: float,
        baseline_tok_60s: float,
    ) -> None:
        # Evaluate baseline-ratio anomaly and create or dedupe the incident.
        req_ratio = requests_60s / max(baseline_req_60s, 1.0)
        tok_ratio = tokens_60s / max(baseline_tok_60s, 1.0)
        max_ratio = max(req_ratio, tok_ratio)
        if max_ratio < LOW_SEVERITY_RATIO:
            return

        token_spike = tok_ratio >= LOW_SEVERITY_RATIO
        request_spike = req_ratio >= LOW_SEVERITY_RATIO
        incident_type = INCIDENT_TYPE_BURN_SPIKE if token_spike else INCIDENT_TYPE_REQUEST_SPIKE
        if not token_spike and not request_spike:
            return

        severity = _severity_for_ratio(max_ratio=max_ratio)
        now = self._now_provider()
        fingerprint = _build_incident_fingerprint(
            project_id=event.project_id,
            incident_type=incident_type,
            provider=event.provider,
            model=event.model,
            environment=event.environment,
        )
        evidence = {
            "current_requests_60s": requests_60s,
            "current_tokens_60s": tokens_60s,
            "baseline_req_60s": baseline_req_60s,
            "baseline_tok_60s": baseline_tok_60s,
            "req_ratio": req_ratio,
            "tok_ratio": tok_ratio,
            "provider": event.provider,
            "model": event.model,
            "environment": event.environment,
            "count": 1,
            "last_seen": now.isoformat(),
            "max_ratio_seen": max_ratio,
        }
        dedup_after = now - timedelta(seconds=self._incident_dedup_window_seconds)
        open_incident = self._incident_repository.get_open_incident_by_fingerprint(
            project_id=event.project_id,
            fingerprint=fingerprint,
            created_after=dedup_after,
        )
        if open_incident is not None:
            current_count = _int_evidence_value(open_incident.evidence.get("count"), default=1)
            existing_max_ratio = _float_evidence_value(open_incident.evidence.get("max_ratio_seen"), default=max_ratio)
            evidence["count"] = current_count + 1
            evidence["max_ratio_seen"] = max(existing_max_ratio, max_ratio)
            updated_severity = _max_severity(severity, open_incident.severity)
            self._incident_repository.update_open_incident_activity(
                incident_id=open_incident.id,
                evidence=evidence,
                last_seen_at=now,
                severity=updated_severity,
            )
            if self._incident_severity_cache is not None:
                self._incident_severity_cache.set(project_id=event.project_id, severity=updated_severity)
            logger.info(
                "Incident deduped and updated",
                extra={"project_id": event.project_id, "incident_id": open_incident.id, "incident_type": incident_type},
            )
            return

        incident = Incident(
            id=str(uuid4()),
            project_id=event.project_id,
            incident_type=incident_type,
            severity=severity,
            status="open",
            created_at=now,
            resolved_at=None,
            evidence=evidence,
            fingerprint=fingerprint,
            last_seen_at=now,
        )
        self._incident_repository.create_incident(incident=incident)
        if self._incident_severity_cache is not None:
            self._incident_severity_cache.set(project_id=event.project_id, severity=severity)
        logger.info(
            "Incident created from ingest",
            extra={"project_id": event.project_id, "incident_type": incident_type, "severity": severity},
        )


def _severity_for_ratio(max_ratio: float) -> str:
    # Map baseline ratio breach to incident severity.
    if max_ratio >= HIGH_SEVERITY_RATIO:
        return "high"
    if max_ratio >= MEDIUM_SEVERITY_RATIO:
        return "medium"
    return "low"


def _max_severity(left: str, right: str) -> str:
    # Return the higher-priority severity.
    ordering = {"low": 1, "medium": 2, "high": 3}
    return left if ordering.get(left, 0) >= ordering.get(right, 0) else right


def _build_incident_fingerprint(
    project_id: str,
    incident_type: str,
    provider: str | None,
    model: str | None,
    environment: str | None,
) -> str:
    # Build deterministic dedupe fingerprint for open incidents.
    return f"{project_id}:{incident_type}:{provider or 'na'}:{model or 'na'}:{environment or 'na'}"


def _int_evidence_value(value: object, default: int) -> int:
    # Parse integer evidence value with default fallback.
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_evidence_value(value: object, default: float) -> float:
    # Parse float evidence value with default fallback.
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
