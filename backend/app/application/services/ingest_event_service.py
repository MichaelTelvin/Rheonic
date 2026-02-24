# Application service for event ingestion.
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.interfaces.event_repository import EventRepository
from app.application.interfaces.incident_repository import IncidentRepository
from app.application.interfaces.project_repository import ProjectRepository
from app.application.interfaces.webhook_dispatcher import WebhookDispatcher
from app.config import app_config
from app.infrastructure.redis.incident_severity_cache import IncidentSeverityCache
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
        incident_severity_cache: IncidentSeverityCache | None,
        baseline_window_count: int,
        incident_dedup_window_seconds: int,
        incident_escalation_window_medium_seconds: int = app_config.default_incident_escalation_window_medium_seconds,
        incident_escalation_window_high_seconds: int = app_config.default_incident_escalation_window_high_seconds,
        incident_escalation_min_hits_medium: int = app_config.default_incident_escalation_min_hits_medium,
        incident_escalation_min_hits_high: int = app_config.default_incident_escalation_min_hits_high,
        incident_escalation_score_threshold_medium: int = app_config.default_incident_escalation_score_threshold_medium,
        incident_escalation_score_threshold_high: int = app_config.default_incident_escalation_score_threshold_high,
        incident_escalation_ttl_seconds: int = app_config.default_incident_escalation_ttl_seconds,
        webhook_dispatcher: WebhookDispatcher | None = None,
        project_repository: ProjectRepository | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        # Initialize service dependencies.
        self._event_repository = event_repository
        self._realtime_counters = realtime_counters
        self._incident_repository = incident_repository
        self._incident_severity_cache = incident_severity_cache
        self._baseline_window_count = baseline_window_count
        self._incident_dedup_window_seconds = incident_dedup_window_seconds
        self._incident_escalation_window_medium_seconds = incident_escalation_window_medium_seconds
        self._incident_escalation_window_high_seconds = incident_escalation_window_high_seconds
        self._incident_escalation_min_hits_medium = incident_escalation_min_hits_medium
        self._incident_escalation_min_hits_high = incident_escalation_min_hits_high
        self._incident_escalation_score_threshold_medium = incident_escalation_score_threshold_medium
        self._incident_escalation_score_threshold_high = incident_escalation_score_threshold_high
        self._incident_escalation_ttl_seconds = incident_escalation_ttl_seconds
        self._webhook_dispatcher = webhook_dispatcher
        self._project_repository = project_repository
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
            self._detect_policy_gap_if_needed(event=event)
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

    def _detect_policy_gap_if_needed(self, *, event: Event) -> None:
        # Record first-seen project provider/model and raise policy-gap incident for protect-enabled projects.
        if self._project_repository is None:
            return
        provider = (event.provider or "").strip()
        model = (event.model or "").strip()
        if not provider or not model:
            return
        first_seen_at = self._now_provider()
        try:
            existing_models_count = self._project_repository.count_project_models(event.project_id)
        except Exception:
            logger.exception(
                "Failed counting project models before first-seen insert",
                extra={"project_id": event.project_id},
            )
            return
        try:
            is_new_combination = self._project_repository.record_project_model_first_seen(
                project_id=event.project_id,
                provider=provider,
                model=model,
                first_seen_at=first_seen_at,
            )
        except Exception:
            logger.exception(
                "Failed recording provider/model first-seen tuple",
                extra={"project_id": event.project_id, "provider": provider, "model": model},
            )
            return
        if not is_new_combination:
            return
        # First-ever model for the project is only recorded for analytics; no incident/webhook.
        if existing_models_count == 0:
            return
        project = self._project_repository.get_project(event.project_id)
        if project is None or not project.protect_enabled:
            return
        incident = Incident(
            id=str(uuid4()),
            project_id=event.project_id,
            incident_type=app_config.incident_type_policy_gap,
            severity="low",
            status="open",
            created_at=first_seen_at,
            resolved_at=None,
            evidence={
                "provider": provider,
                "model": model,
                "environment": event.environment,
                "first_seen_at": first_seen_at.isoformat(),
                "source": "policy_gap",
            },
            fingerprint=_build_incident_fingerprint(
                project_id=event.project_id,
                incident_type=app_config.incident_type_policy_gap,
                provider=provider,
                model=model,
                environment=None,
            ),
            last_seen_at=first_seen_at,
        )
        self._incident_repository.create_incident(incident=incident)
        if self._webhook_dispatcher is not None:
            try:
                self._webhook_dispatcher.enqueue(
                    project_id=event.project_id,
                    event_type="policy_gap.detected",
                    payload={
                        "event": "policy_gap.detected",
                        "project_id": event.project_id,
                        "provider": provider,
                        "model": model,
                        "incident_id": incident.id,
                        "first_seen_at": first_seen_at.isoformat(),
                        "sent_at": self._now_provider().isoformat(),
                    },
                )
            except Exception:
                logger.exception("Failed to enqueue policy-gap webhook", extra={"project_id": event.project_id})

    def _has_open_incident_for_dimension(self, event: Event) -> bool:
        # Freeze baseline updates while any open anomaly incident exists for this event dimension.
        created_after = datetime.fromtimestamp(0, tz=timezone.utc)
        for incident_type in (app_config.incident_type_burn_spike, app_config.incident_type_request_spike):
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
        if max_ratio < app_config.incident_severity_ratio_low:
            return

        token_spike = tok_ratio >= app_config.incident_severity_ratio_low
        request_spike = req_ratio >= app_config.incident_severity_ratio_low
        incident_type = app_config.incident_type_burn_spike if token_spike else app_config.incident_type_request_spike
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
            evidence = {**open_incident.evidence, **evidence}
            current_count = _int_evidence_value(open_incident.evidence.get("count"), default=1)
            existing_max_ratio = _float_evidence_value(open_incident.evidence.get("max_ratio_seen"), default=max_ratio)
            evidence["count"] = current_count + 1
            evidence["max_ratio_seen"] = max(existing_max_ratio, max_ratio)
            updated_severity = open_incident.severity
            escalation_payload = self._evaluate_incident_escalation(
                project_id=event.project_id,
                incident_type=incident_type,
                current_severity=open_incident.severity,
                max_ratio=max_ratio,
                now=now,
            )
            evidence["escalation"] = escalation_payload["evidence"]
            escalated_severity = escalation_payload["severity"]
            if escalated_severity is not None:
                updated_severity = escalated_severity
            self._incident_repository.update_open_incident_activity(
                incident_id=open_incident.id,
                evidence=evidence,
                last_seen_at=now,
                severity=updated_severity,
            )
            if open_incident.severity != "high" and updated_severity == "high":
                self._enqueue_high_incident_webhook(
                    incident_id=open_incident.id,
                    event=event,
                    incident_type=incident_type,
                    previous_severity=open_incident.severity,
                    severity=updated_severity,
                    created_at=open_incident.created_at,
                    last_seen_at=now,
                    evidence=evidence,
                    requests_60s=requests_60s,
                    tokens_60s=tokens_60s,
                    source="escalation",
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
        if severity == "high":
            self._enqueue_high_incident_webhook(
                incident_id=incident.id,
                event=event,
                incident_type=incident_type,
                previous_severity=None,
                severity=severity,
                created_at=incident.created_at,
                last_seen_at=now,
                evidence=evidence,
                requests_60s=requests_60s,
                tokens_60s=tokens_60s,
                source="opened_high",
            )
        if self._incident_severity_cache is not None:
            self._incident_severity_cache.set(project_id=event.project_id, severity=severity)
        logger.info(
            "Incident created from ingest",
            extra={"project_id": event.project_id, "incident_type": incident_type, "severity": severity},
        )

    def _evaluate_incident_escalation(
        self,
        *,
        project_id: str,
        incident_type: str,
        current_severity: str,
        max_ratio: float,
        now: datetime,
    ) -> dict[str, object]:
        # Evaluate severity escalation from repeated anomaly hits within configured windows.
        hit_score = _score_for_escalation_ratio(max_ratio)
        default_evidence = {
            "hit_count_medium_window": 0,
            "score_sum_medium_window": 0,
            "window_medium_seconds": self._incident_escalation_window_medium_seconds,
            "hit_count_high_window": 0,
            "score_sum_high_window": 0,
            "window_high_seconds": self._incident_escalation_window_high_seconds,
            "last_hit_ratio": max_ratio,
            "last_hit_score": hit_score,
            "applied": "none",
        }
        if hit_score == 0 or current_severity == "high":
            return {"severity": None, "evidence": default_evidence}

        now_unix = int(now.timestamp())
        prune_before = now_unix - max(
            self._incident_escalation_window_medium_seconds,
            self._incident_escalation_window_high_seconds,
        )
        hits = self._realtime_counters.record_incident_escalation_hit(
            project_id=project_id,
            incident_type=incident_type,
            ts_unix=now_unix,
            score=hit_score,
            ratio=max_ratio,
            prune_before_unix=prune_before,
            ttl_seconds=self._incident_escalation_ttl_seconds,
        )
        medium_cutoff = now_unix - self._incident_escalation_window_medium_seconds
        high_cutoff = now_unix - self._incident_escalation_window_high_seconds
        medium_hits = [hit for hit in hits if int(hit.get("ts", 0)) >= medium_cutoff]
        high_hits = [hit for hit in hits if int(hit.get("ts", 0)) >= high_cutoff]
        hit_count_m = len(medium_hits)
        score_sum_m = sum(int(hit.get("score", 0)) for hit in medium_hits)
        hit_count_h = len(high_hits)
        score_sum_h = sum(int(hit.get("score", 0)) for hit in high_hits)
        max_score_h = max((int(hit.get("score", 0)) for hit in high_hits), default=0)

        applied = "none"
        next_severity: str | None = None
        high_threshold_met = (
            hit_count_h >= self._incident_escalation_min_hits_high
            and score_sum_h >= self._incident_escalation_score_threshold_high
        )
        medium_threshold_met = (
            hit_count_m >= self._incident_escalation_min_hits_medium
            and score_sum_m >= self._incident_escalation_score_threshold_medium
        )
        if current_severity == "low":
            if high_threshold_met and max_score_h >= app_config.incident_escalation_high_score_required:
                next_severity = "high"
                applied = "low_to_high"
            elif medium_threshold_met:
                next_severity = "medium"
                applied = "low_to_medium"
        elif current_severity == "medium":
            if high_threshold_met:
                next_severity = "high"
                applied = "medium_to_high"

        escalation_evidence = {
            "hit_count_medium_window": hit_count_m,
            "score_sum_medium_window": score_sum_m,
            "window_medium_seconds": self._incident_escalation_window_medium_seconds,
            "hit_count_high_window": hit_count_h,
            "score_sum_high_window": score_sum_h,
            "window_high_seconds": self._incident_escalation_window_high_seconds,
            "last_hit_ratio": max_ratio,
            "last_hit_score": hit_score,
            "applied": applied,
        }
        return {"severity": next_severity, "evidence": escalation_evidence}

    def _enqueue_high_incident_webhook(
        self,
        *,
        incident_id: str,
        event: Event,
        incident_type: str,
        previous_severity: str | None,
        severity: str,
        created_at: datetime,
        last_seen_at: datetime,
        evidence: dict[str, object],
        requests_60s: int,
        tokens_60s: int,
        source: str,
    ) -> None:
        # Enqueue high-severity incident webhook if dispatcher is configured.
        if severity != "high" or self._webhook_dispatcher is None:
            return
        threshold_req_60s = None
        threshold_tok_60s = None
        if self._project_repository is not None:
            project = self._project_repository.get_project(event.project_id)
            if project is not None:
                threshold_req_60s = project.protect_max_req_per_min
                threshold_tok_60s = project.protect_max_tok_per_min
        payload = {
            "event": "incident.high",
            "project_id": event.project_id,
            "incident_id": incident_id,
            "incident_type": incident_type,
            "prev_severity": previous_severity,
            "severity": severity,
            "provider": event.provider,
            "model": event.model,
            "environment": event.environment,
            "created_at": created_at.isoformat(),
            "last_seen_at": last_seen_at.isoformat(),
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "incident": {
                "id": incident_id,
                "type": incident_type,
                "severity": severity,
                "status": "open",
                "created_at": created_at.isoformat(),
                "last_seen_at": last_seen_at.isoformat(),
                "evidence": evidence,
            },
            "snapshot": {
                "requests_60s": requests_60s,
                "tokens_60s": tokens_60s,
                "threshold_req_60s": threshold_req_60s,
                "threshold_tok_60s": threshold_tok_60s,
            },
        }
        try:
            self._webhook_dispatcher.enqueue(
                project_id=event.project_id,
                payload=payload,
                event_type="incident.high",
            )
        except Exception:
            logger.exception("Failed to enqueue high-incident webhook", extra={"project_id": event.project_id})


def _severity_for_ratio(max_ratio: float) -> str:
    # Map baseline ratio breach to incident severity.
    if max_ratio >= app_config.incident_severity_ratio_high:
        return "high"
    if max_ratio >= app_config.incident_severity_ratio_medium:
        return "medium"
    return "low"


def _max_severity(left: str, right: str) -> str:
    # Return the higher-priority severity.
    ordering = {"low": 1, "medium": 2, "high": 3}
    return left if ordering.get(left, 0) >= ordering.get(right, 0) else right


def _score_for_escalation_ratio(max_ratio: float) -> int:
    # Map incident ratio to escalation score buckets.
    if max_ratio >= app_config.incident_escalation_score_ratio_high:
        return 3
    if max_ratio >= app_config.incident_escalation_score_ratio_medium:
        return 2
    if max_ratio >= app_config.incident_escalation_score_ratio_low:
        return 1
    return 0


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
