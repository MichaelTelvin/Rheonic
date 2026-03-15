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
from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.loop_suspect_detector import LoopSuspectDetector
from app.domain.detectors.near_cap_detector import NearCapDetector
from app.domain.detectors.registry import DetectorRegistry
from app.domain.detectors.retry_storm_detector import RetryStormDetector
from app.domain.detectors.token_explosion_detector import TokenExplosionDetector
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
        token_explosion_ratio: float = app_config.token_explosion_ratio,
        token_explosion_abs: int = app_config.token_explosion_abs,
    ) -> None:
        self._event_repository = event_repository
        self._realtime_counters = realtime_counters
        self._incident_repository = incident_repository
        self._project_repository = project_repository
        self._retry_storm_window_seconds = retry_storm_window_seconds
        self._retry_storm_count = retry_storm_count
        self._loop_window_seconds = loop_window_seconds
        self._loop_count = loop_count
        self._token_explosion_ratio = token_explosion_ratio
        self._token_explosion_abs = token_explosion_abs
        self._incident_dedup_window_seconds = incident_dedup_window_seconds
        self._detector_registry = DetectorRegistry(
            detectors=[
                NearCapDetector(),
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
            project = self._project_repository.get_project(event.project_id) if self._project_repository is not None else None
            req_cap = project.protect_max_req_per_min if project is not None else None
            tok_cap = project.protect_max_tok_per_min if project is not None else None
            protect_enabled = bool(project.protect_enabled) if project is not None else False
            mode = "protect" if protect_enabled else "observe"
            recent_events = self._event_repository.list_recent(project_id=event.project_id, limit=200,  provider=provider)
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
                current_event=event,
                recent_events=recent_events,
                warn_ratio=app_config.protect_near_cap_factor,
                predictive_near_cap=False,
                retry_storm_window_seconds=self._retry_storm_window_seconds,
                retry_storm_count=self._retry_storm_count,
                loop_window_seconds=self._loop_window_seconds,
                loop_count=self._loop_count,
                token_explosion_ratio=self._token_explosion_ratio,
                token_explosion_abs=self._token_explosion_abs,
            )
            signals = self._detector_registry.detect(ctx)
            cap_breach_signals = self._cap_breach_signal_if_any(ctx)
            if cap_breach_signals:
                # Dominance L3: cap_breach suppresses all other signals for this ingest event.
                # A live cap breach supersedes only recent open near-cap incidents from the same provider.
                self._incident_repository.resolve_open_incidents_by_type(
                    project_id=event.project_id,
                    provider=provider,
                    incident_type=app_config.incident_type_near_cap,
                    resolved_at=self._now_provider(),
                    created_after=self._now_provider() - timedelta(seconds=self._incident_dedup_window_seconds),
                )
                signals = cap_breach_signals
            else:
                near_cap_signals = [signal for signal in signals if signal.detector == "near_cap"]
                if near_cap_signals:
                    # Dominance L2: near_cap suppresses behavioral signals for this ingest event.
                    signals = near_cap_signals
                # Dominance L1: behavioral signals may coexist.
            self._incident_manager.process_signals(
                project_id=event.project_id,
                provider=provider,
                model=event.model,
                environment=event.environment,
                now=self._now_provider(),
                signals=signals,
                mode=mode,
            )
            logger.info("Event ingested", extra={"project_id": event.project_id, "event_id": event.id})
        except Exception:
            logger.exception("Ingest service failed", extra={"project_id": event.project_id})
            raise

    def _cap_breach_signal_if_any(self, ctx: DetectionContext) -> list[Signal]:
        req_breach = bool(ctx.req_cap is not None and ctx.current_requests_60s >= ctx.req_cap)
        tok_breach = bool(ctx.tok_cap is not None and ctx.current_tokens_60s >= ctx.tok_cap)
        if not (req_breach or tok_breach):
            return []
        reason = "tok_cap_breach" if tok_breach else "req_cap_breach"
        evidence: dict[str, object] = {
            "provider": ctx.provider,
            "model": ctx.model,
            "environment": ctx.environment,
            "requests_60s": ctx.current_requests_60s,
            "tokens_60s": ctx.current_tokens_60s,
            "req_cap": ctx.req_cap,
            "tok_cap": ctx.tok_cap,
            "estimated_next_tokens": ctx.estimated_next_tokens,
            "req_cap_breach": req_breach,
            "tok_cap_breach": tok_breach,
            "reason": reason,
        }
        return [
            Signal(
                detector="cap_breach",
                scope_provider=ctx.provider,
                fingerprint=f"{ctx.project_id}:{ctx.provider}:cap_breach",
                evidence=evidence,
            )
        ]

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
        project = self._project_repository.get_project(event.project_id)
        if self._webhook_dispatcher is not None and project is not None and bool(project.protect_enabled):
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
                        "sent_at": first_seen_at.isoformat(),
                    },
                )
            except Exception:
                logger.exception("Failed to enqueue policy-gap webhook", extra={"project_id": event.project_id})
