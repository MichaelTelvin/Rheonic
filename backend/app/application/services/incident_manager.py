from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.interfaces.incident_repository import IncidentRepository
from app.application.interfaces.project_repository import ProjectRepository
from app.application.interfaces.webhook_dispatcher import WebhookDispatcher
from app.application.provider_scope import scoped_project_provider_id
from app.config import app_config
from app.domain.detectors.contracts import Signal
from app.domain.models.incident import Incident
from app.infrastructure.redis.incident_severity_cache import IncidentSeverityCache
from app.logger import get_logger

logger = get_logger(__name__)


class IncidentManager:
    # Persists and updates incidents from detector signals.

    def __init__(
        self,
        *,
        incident_repository: IncidentRepository,
        realtime_counters: RealtimeCounterStore,
        incident_severity_cache: IncidentSeverityCache | None,
        incident_dedup_window_seconds: int,
        incident_escalation_window_medium_seconds: int,
        incident_escalation_window_high_seconds: int,
        incident_escalation_min_hits_medium: int,
        incident_escalation_min_hits_high: int,
        incident_escalation_score_threshold_medium: int,
        incident_escalation_score_threshold_high: int,
        incident_escalation_ttl_seconds: int,
        webhook_dispatcher: WebhookDispatcher | None = None,
        project_repository: ProjectRepository | None = None,
    ) -> None:
        self._incident_repository = incident_repository
        self._realtime_counters = realtime_counters
        self._incident_severity_cache = incident_severity_cache
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

    def process_signals(
        self,
        *,
        project_id: str,
        provider: str,
        model: str | None,
        environment: str | None,
        requests_60s: int,
        tokens_60s: int,
        now: datetime,
        signals: list[Signal],
    ) -> None:
        for signal in signals:
            self._process_signal(
                project_id=project_id,
                provider=provider,
                model=model,
                environment=environment,
                requests_60s=requests_60s,
                tokens_60s=tokens_60s,
                now=now,
                signal=signal,
            )

    def _process_signal(
        self,
        *,
        project_id: str,
        provider: str,
        model: str | None,
        environment: str | None,
        requests_60s: int,
        tokens_60s: int,
        now: datetime,
        signal: Signal,
    ) -> None:
        incident_type = _incident_type_from_detector(signal.detector)
        evidence = dict(signal.evidence)
        evidence["detector"] = signal.detector
        evidence["provider"] = provider
        evidence["model"] = model
        evidence["environment"] = environment
        evidence["last_seen"] = now.isoformat()
        evidence["count"] = 1
        evidence["max_ratio_seen"] = _max_ratio_from_evidence(evidence)
        dedup_after = now - timedelta(seconds=self._incident_dedup_window_seconds)
        open_incident = self._incident_repository.get_open_incident_by_fingerprint(
            project_id=project_id,
            provider=provider,
            fingerprint=signal.fingerprint,
            created_after=dedup_after,
        )
        if open_incident is not None:
            evidence = {**open_incident.evidence, **evidence}
            evidence["count"] = _int_evidence_value(open_incident.evidence.get("count"), default=1) + 1
            max_ratio = max(
                _float_evidence_value(open_incident.evidence.get("max_ratio_seen"), default=0.0),
                _max_ratio_from_evidence(evidence),
            )
            evidence["max_ratio_seen"] = max_ratio
            updated_severity = open_incident.severity
            escalation_payload = self._evaluate_incident_escalation(
                project_id=project_id,
                provider=provider,
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
                    project_id=project_id,
                    provider=provider,
                    model=model,
                    environment=environment,
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
            self._update_severity_cache(project_id=project_id, provider=provider, severity=updated_severity)
            return

        incident = Incident(
            id=str(uuid4()),
            project_id=project_id,
            provider=provider,
            incident_type=incident_type,
            severity=signal.severity,
            status="open",
            created_at=now,
            resolved_at=None,
            evidence=evidence,
            fingerprint=signal.fingerprint,
            last_seen_at=now,
        )
        self._incident_repository.create_incident(incident=incident)
        if incident.severity == "high":
            self._enqueue_high_incident_webhook(
                incident_id=incident.id,
                project_id=project_id,
                provider=provider,
                model=model,
                environment=environment,
                incident_type=incident_type,
                previous_severity=None,
                severity=incident.severity,
                created_at=incident.created_at,
                last_seen_at=now,
                evidence=evidence,
                requests_60s=requests_60s,
                tokens_60s=tokens_60s,
                source="opened_high",
            )
        self._update_severity_cache(project_id=project_id, provider=provider, severity=incident.severity)

    def _update_severity_cache(self, *, project_id: str, provider: str, severity: str) -> None:
        if self._incident_severity_cache is None:
            return
        self._incident_severity_cache.set(
            project_id=scoped_project_provider_id(project_id, provider),
            severity=severity,
        )

    def _evaluate_incident_escalation(
        self,
        *,
        project_id: str,
        provider: str,
        incident_type: str,
        current_severity: str,
        max_ratio: float,
        now: datetime,
    ) -> dict[str, object]:
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
            project_id=scoped_project_provider_id(project_id, provider),
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
        project_id: str,
        provider: str,
        model: str | None,
        environment: str | None,
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
        if severity != "high" or self._webhook_dispatcher is None:
            return
        threshold_req_60s = None
        threshold_tok_60s = None
        if self._project_repository is not None:
            project = self._project_repository.get_project(project_id)
            if project is not None:
                threshold_req_60s = project.protect_max_req_per_min
                threshold_tok_60s = project.protect_max_tok_per_min
        payload = {
            "event": "incident.high",
            "project_id": project_id,
            "incident_id": incident_id,
            "incident_type": incident_type,
            "prev_severity": previous_severity,
            "severity": severity,
            "provider": provider,
            "model": model,
            "environment": environment,
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
                project_id=project_id,
                payload=payload,
                event_type="incident.high",
            )
        except Exception:
            logger.exception("Failed to enqueue high-incident webhook", extra={"project_id": project_id})


def _incident_type_from_detector(detector: str) -> str:
    if detector == "tok_spike":
        return app_config.incident_type_burn_spike
    if detector == "req_spike":
        return app_config.incident_type_request_spike
    return detector


def _score_for_escalation_ratio(max_ratio: float) -> int:
    if max_ratio >= app_config.incident_escalation_score_ratio_high:
        return 3
    if max_ratio >= app_config.incident_escalation_score_ratio_medium:
        return 2
    if max_ratio >= app_config.incident_escalation_score_ratio_low:
        return 1
    return 0


def _int_evidence_value(value: object, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_evidence_value(value: object, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _max_ratio_from_evidence(evidence: dict[str, object]) -> float:
    req_ratio = _float_evidence_value(evidence.get("req_ratio"), default=0.0)
    tok_ratio = _float_evidence_value(evidence.get("tok_ratio"), default=0.0)
    return max(req_ratio, tok_ratio)
