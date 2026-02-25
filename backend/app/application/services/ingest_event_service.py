# Application service for event ingestion.
from collections.abc import Callable
from datetime import datetime, timezone

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.interfaces.event_repository import EventRepository
from app.application.interfaces.incident_repository import IncidentRepository
from app.application.interfaces.project_repository import ProjectRepository
from app.application.interfaces.webhook_dispatcher import WebhookDispatcher
from app.application.provider_scope import scoped_project_provider_id
from app.application.services.incident_manager import IncidentManager
from app.config import app_config
from app.domain.detectors.baseline_gate import BaselineGate
from app.domain.detectors.contracts import DetectionContext
from app.domain.detectors.loop_suspect_detector import LoopSuspectDetector
from app.domain.detectors.registry import DetectorRegistry
from app.domain.detectors.req_spike_detector import ReqSpikeDetector
from app.domain.detectors.retry_storm_detector import RetryStormDetector
from app.domain.detectors.tok_spike_detector import TokSpikeDetector
from app.domain.detectors.token_explosion_detector import TokenExplosionDetector
from app.domain.models.event import Event
from app.infrastructure.redis.incident_severity_cache import IncidentSeverityCache
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
        baseline_gate_min_windows: int = app_config.baseline_gate_min_windows,
        baseline_gate_min_baseline_req: float = app_config.baseline_gate_min_baseline_req,
        baseline_gate_min_baseline_tok: float = app_config.baseline_gate_min_baseline_tok,
        baseline_gate_early_abs_req_60s: int = app_config.baseline_gate_early_abs_req_60s,
        baseline_gate_early_abs_tok_60s: int = app_config.baseline_gate_early_abs_tok_60s,
        detectors_req_spike_ratio_low: float = app_config.detectors_req_spike_ratio_low,
        detectors_req_spike_delta_low: float = app_config.detectors_req_spike_delta_low,
        detectors_tok_spike_ratio_low: float = app_config.detectors_tok_spike_ratio_low,
        detectors_tok_spike_delta_low: float = app_config.detectors_tok_spike_delta_low,
    ) -> None:
        self._event_repository = event_repository
        self._realtime_counters = realtime_counters
        self._incident_repository = incident_repository
        self._baseline_window_count = baseline_window_count
        self._project_repository = project_repository
        self._webhook_dispatcher = webhook_dispatcher
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._detector_registry = DetectorRegistry(
            detectors=[
                TokSpikeDetector(),
                ReqSpikeDetector(),
                RetryStormDetector(),
                LoopSuspectDetector(),
                TokenExplosionDetector(),
            ]
        )
        self._baseline_gate = BaselineGate(
            min_windows=baseline_gate_min_windows,
            min_baseline_req=baseline_gate_min_baseline_req,
            min_baseline_tok=baseline_gate_min_baseline_tok,
            early_abs_req_60s=baseline_gate_early_abs_req_60s,
            early_abs_tok_60s=baseline_gate_early_abs_tok_60s,
        )
        self._req_spike_ratio_low = detectors_req_spike_ratio_low
        self._req_spike_delta_low = detectors_req_spike_delta_low
        self._tok_spike_ratio_low = detectors_tok_spike_ratio_low
        self._tok_spike_delta_low = detectors_tok_spike_delta_low
        self._incident_manager = IncidentManager(
            incident_repository=incident_repository,
            realtime_counters=realtime_counters,
            incident_severity_cache=incident_severity_cache,
            incident_dedup_window_seconds=incident_dedup_window_seconds,
            incident_escalation_window_medium_seconds=incident_escalation_window_medium_seconds,
            incident_escalation_window_high_seconds=incident_escalation_window_high_seconds,
            incident_escalation_min_hits_medium=incident_escalation_min_hits_medium,
            incident_escalation_min_hits_high=incident_escalation_min_hits_high,
            incident_escalation_score_threshold_medium=incident_escalation_score_threshold_medium,
            incident_escalation_score_threshold_high=incident_escalation_score_threshold_high,
            incident_escalation_ttl_seconds=incident_escalation_ttl_seconds,
            webhook_dispatcher=webhook_dispatcher,
            project_repository=project_repository,
        )

    def ingest(self, event: Event) -> None:
        # Persist a single event, update counters, run detectors, and process resulting signals.
        try:
            provider = (event.provider or "").strip() or "unknown"
            scoped_id = scoped_project_provider_id(event.project_id, provider)
            self._event_repository.add(event)
            self._realtime_counters.increment_project_60s(
                project_id=scoped_id,
                total_tokens=event.total_tokens,
            )
            requests_60s, tokens_60s = self._realtime_counters.get_project_60s(project_id=scoped_id)
            self._detect_policy_gap_if_needed(event=event)
            try:
                if self._has_open_incident_for_dimension(event=event, provider=provider):
                    baseline_req_60s, baseline_tok_60s = self._realtime_counters.get_baseline_snapshot(
                        project_id=scoped_id,
                        max_windows=self._baseline_window_count,
                    )
                else:
                    baseline_req_60s, baseline_tok_60s = self._realtime_counters.record_baseline_snapshot(
                        project_id=scoped_id,
                        requests_60s=requests_60s,
                        tokens_60s=tokens_60s,
                        max_windows=self._baseline_window_count,
                    )
                baseline_windows = self._realtime_counters.get_baseline_sample_count(
                    project_id=scoped_id,
                    max_windows=self._baseline_window_count,
                )
                gate = self._baseline_gate.evaluate(
                    current_requests_60s=requests_60s,
                    current_tokens_60s=tokens_60s,
                    baseline_req_60s=baseline_req_60s,
                    baseline_tok_60s=baseline_tok_60s,
                    baseline_windows=baseline_windows,
                )
                ctx = DetectionContext(
                    project_id=event.project_id,
                    provider=provider,
                    model=event.model,
                    feature=None,
                    environment=event.environment,
                    current_requests_60s=requests_60s,
                    current_tokens_60s=tokens_60s,
                    baseline_req_60s=baseline_req_60s,
                    baseline_tok_60s=baseline_tok_60s,
                    baseline_windows=baseline_windows,
                    gate=gate,
                    req_spike_ratio_low=self._req_spike_ratio_low,
                    req_spike_delta_low=self._req_spike_delta_low,
                    tok_spike_ratio_low=self._tok_spike_ratio_low,
                    tok_spike_delta_low=self._tok_spike_delta_low,
                )
                signals = self._detector_registry.detect(ctx)
                self._incident_manager.process_signals(
                    project_id=event.project_id,
                    provider=provider,
                    model=event.model,
                    environment=event.environment,
                    requests_60s=requests_60s,
                    tokens_60s=tokens_60s,
                    now=self._now_provider(),
                    signals=signals,
                )
            except Exception:
                logger.exception("Anomaly evaluation failed during ingest", extra={"project_id": event.project_id})
            logger.info("Event ingested", extra={"project_id": event.project_id, "event_id": event.id})
        except Exception:
            logger.exception("Ingest service failed", extra={"project_id": event.project_id})
            raise

    def _detect_policy_gap_if_needed(self, *, event: Event) -> None:
        # Record first-seen project/provider/model tuples and emit one-time policy-gap webhook notification.
        if self._project_repository is None:
            return
        provider = (event.provider or "").strip()
        model = (event.model or "").strip()
        if not provider or not model:
            return
        first_seen_at = self._now_provider()
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
        logger.info(
            "Policy gap detected: first-seen provider/model tuple",
            extra={
                "project_id": event.project_id,
                "provider": provider,
                "model": model,
                "first_seen_at": first_seen_at.isoformat(),
            },
        )
        if self._webhook_dispatcher is not None:
            try:
                self._webhook_dispatcher.enqueue(
                    project_id=event.project_id,
                    event_type="policy_gap.detected",
                    payload={
                        "event_type": "policy_gap.detected",
                        "project_id": event.project_id,
                        "provider": provider,
                        "model": model,
                        "first_seen_at": first_seen_at.isoformat(),
                        "sent_at": self._now_provider().isoformat(),
                    },
                )
            except Exception:
                logger.exception("Failed to enqueue policy-gap webhook", extra={"project_id": event.project_id})

    def _has_open_incident_for_dimension(self, event: Event, provider: str) -> bool:
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
                provider=provider,
                fingerprint=fingerprint,
                created_after=created_after,
            )
            if open_incident is not None:
                return True
        return False


def _build_incident_fingerprint(
    project_id: str,
    incident_type: str,
    provider: str | None,
    model: str | None,
    environment: str | None,
) -> str:
    return f"{project_id}:{incident_type}:{provider or 'na'}:{model or 'na'}:{environment or 'na'}"


def _severity_for_ratio(max_ratio: float) -> str:
    # Retained for compatibility with existing tests.
    if max_ratio >= app_config.incident_severity_ratio_high:
        return "high"
    if max_ratio >= app_config.incident_severity_ratio_medium:
        return "medium"
    return "low"
