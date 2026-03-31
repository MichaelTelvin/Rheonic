# Application service for event ingestion.
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.interfaces.event_repository import EventRepository
from app.application.interfaces.incident_repository import IncidentRepository
from app.application.interfaces.project_repository import ProjectRepository
from app.application.interfaces.webhook_dispatcher import WebhookDispatcher
from app.application.provider_scope import scoped_project_provider_id
from app.application.services.incident_manager import IncidentManager
from app.application.services.transport_service import TransportService
from app.config import app_config
from app.domain.detectors.contracts import DetectionContext
from app.domain.detectors.loop_suspect_detector import LoopSuspectDetector
from app.domain.detectors.registry import DetectorRegistry
from app.domain.detectors.retry_storm_detector import RetryStormDetector
from app.domain.detectors.token_explosion_detector import TokenExplosionDetector, resolve_previous_estimated_tokens
from app.domain.models.event import Event
from app.logger import get_logger

logger = get_logger(__name__)


class IngestEventService:
    # Persist event, update rolling counters, run deterministic detectors, and upsert incidents.

    def __init__(
        self,
        event_repository: EventRepository,
        realtime_counters: RealtimeCounterStore,
        incident_repository: IncidentRepository,
        incident_dedup_window_seconds: int,
        webhook_dispatcher: WebhookDispatcher | None = None,
        transport_service: TransportService | None = None,
        project_repository: ProjectRepository | None = None,
        now_provider: Callable[[], datetime] | None = None,
        retry_storm_window_seconds: int = app_config.retry_storm_window_seconds,
        retry_storm_count: int = app_config.retry_storm_count,
        loop_window_seconds: int = app_config.loop_window_seconds,
        loop_count: int = app_config.loop_count,
        loop_max_gap_seconds: float = app_config.loop_max_gap_seconds,
        loop_concurrency_threshold: int = app_config.loop_concurrency_threshold,
        token_explosion_ratio: float = app_config.token_explosion_ratio,
        token_explosion_abs: int = app_config.token_explosion_abs,
        token_explosion_growth_ratio: float = app_config.token_explosion_growth_ratio,
        token_explosion_growth_count: int = app_config.token_explosion_growth_count,
        token_explosion_growth_min_tokens: int = app_config.token_explosion_growth_min_tokens,
        token_explosion_concurrency_threshold: int = app_config.token_explosion_concurrency_threshold,
    ) -> None:
        self._event_repository = event_repository
        self._realtime_counters = realtime_counters
        self._incident_repository = incident_repository
        self._project_repository = project_repository
        self._retry_storm_window_seconds = retry_storm_window_seconds
        self._retry_storm_count = retry_storm_count
        self._loop_window_seconds = loop_window_seconds
        self._loop_count = loop_count
        self._loop_max_gap_seconds = loop_max_gap_seconds
        self._loop_concurrency_threshold = loop_concurrency_threshold
        self._token_explosion_ratio = token_explosion_ratio
        self._token_explosion_abs = token_explosion_abs
        self._token_explosion_growth_ratio = token_explosion_growth_ratio
        self._token_explosion_growth_count = token_explosion_growth_count
        self._token_explosion_growth_min_tokens = token_explosion_growth_min_tokens
        self._token_explosion_concurrency_threshold = token_explosion_concurrency_threshold
        self._incident_dedup_window_seconds = incident_dedup_window_seconds
        self._detector_registry = DetectorRegistry(
            detectors=[
                RetryStormDetector(),
                LoopSuspectDetector(),
                TokenExplosionDetector(),
            ]
        )
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._incident_manager = IncidentManager(
            incident_repository=incident_repository,
            incident_dedup_window_seconds=incident_dedup_window_seconds,
            webhook_dispatcher=webhook_dispatcher,
            transport_service=transport_service,
        )
        self._webhook_dispatcher = webhook_dispatcher

    def ingest(self, event: Event) -> None:
        # Persist a single event, update counters, and process detector signals.
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
            project = (
                self._project_repository.get_project(event.project_id) if self._project_repository is not None else None
            )
            req_cap = project.protect_max_req_per_min if project is not None else None
            tok_cap = project.protect_max_tok_per_min if project is not None else None
            protect_enabled = bool(project.protect_enabled) if project is not None else False
            mode = "protect" if protect_enabled else "observe"
            recent_limit = max(int(self._retry_storm_count), int(self._loop_count)) + 8
            recent_events = self._event_repository.list_recent(
                project_id=event.project_id,
                limit=recent_limit,
                provider=provider,
            )
            previous_estimated_tokens = resolve_previous_estimated_tokens(
                recent_events=recent_events,
                provider=provider,
                model=event.model,
                request_endpoint=event.request_endpoint,
                request_feature=event.request_feature,
                current_event=event,
            )
            ctx = DetectionContext(
                project_id=event.project_id,
                provider=provider,
                model=event.model,
                environment=event.environment,
                now=self._now_provider(),
                current_requests_60s=requests_60s,
                current_tokens_60s=tokens_60s,
                req_cap=req_cap,
                tok_cap=tok_cap,
                protect_enabled=protect_enabled,
                request_endpoint=event.request_endpoint,
                request_feature=event.request_feature,
                estimated_next_tokens=event.total_tokens,
                token_explosion_tokens=event.token_explosion_tokens,
                previous_estimated_tokens=previous_estimated_tokens,
                current_event=event,
                recent_events=recent_events,
                retry_storm_window_seconds=self._retry_storm_window_seconds,
                retry_storm_count=self._retry_storm_count,
                loop_window_seconds=self._loop_window_seconds,
                loop_count=self._loop_count,
                loop_max_gap_seconds=self._loop_max_gap_seconds,
                loop_concurrency_threshold=self._loop_concurrency_threshold,
                token_explosion_ratio=self._token_explosion_ratio,
                token_explosion_abs=self._token_explosion_abs,
                token_explosion_growth_ratio=self._token_explosion_growth_ratio,
                token_explosion_growth_count=self._token_explosion_growth_count,
                token_explosion_growth_min_tokens=self._token_explosion_growth_min_tokens,
                token_explosion_concurrency_threshold=self._token_explosion_concurrency_threshold,
            )
            signals = self._detector_registry.detect(ctx)
            for signal in signals:
                signal.evidence.setdefault("trigger_event_id", event.id)
                signal.evidence.setdefault("trigger_event_ts", event.ts.isoformat())
                signal.evidence.setdefault("trigger_request_endpoint", event.request_endpoint)
                signal.evidence.setdefault("trigger_request_feature", event.request_feature)
            if protect_enabled and self._has_active_block_incident(
                project_id=event.project_id,
                provider=provider,
                now=self._now_provider(),
            ):
                signals = [signal for signal in signals if signal.detector == app_config.incident_type_block]
            self._incident_manager.process_signals(
                project_id=event.project_id,
                provider=provider,
                model=event.model,
                environment=event.environment,
                now=self._now_provider(),
                signals=signals,
                mode=mode,
            )
        except Exception:
            logger.exception("Ingest service failed", extra={"project_id": event.project_id})
            raise

    def _has_active_block_incident(self, *, project_id: str, provider: str, now: datetime) -> bool:
        active_after = now - timedelta(seconds=max(int(self._incident_dedup_window_seconds), 1))
        for incident in self._incident_repository.list_open_by_project_provider(
            project_id=project_id, provider=provider
        ):
            if incident.incident_type != app_config.incident_type_block:
                continue
            if (incident.last_seen_at or incident.created_at) >= active_after:
                return True
        return False

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
            is_new_combination, had_existing_models = self._project_repository.record_project_model_first_seen(
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
        if not had_existing_models:
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
        project = self._project_repository.get_project(event.project_id)
        if self._webhook_dispatcher is not None and project is not None:
            try:
                self._webhook_dispatcher.enqueue(
                    project_id=event.project_id,
                    event_type="policy_gap.detected",
                    payload={
                        "event": "policy_gap.detected",
                        "project_id": event.project_id,
                        "provider": provider,
                        "model": model,
                        "first_seen_at": first_seen_at.isoformat(),
                        "sent_at": first_seen_at.isoformat(),
                    },
                )
            except Exception:
                logger.exception("Failed to enqueue policy-gap webhook", extra={"project_id": event.project_id})
