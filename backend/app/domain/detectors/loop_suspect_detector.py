from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector
from app.domain.detectors.model_normalization import normalized_model_name
from app.domain.models.event import Event


class LoopSuspectDetector(Detector):
    # Detect rapid consecutive traffic with the same signature so scattered
    # repetition or high-concurrency bursts do not look like a stuck loop.
    def detect(self, ctx: DetectionContext) -> list[Signal]:
        if not ctx.recent_events:
            return []
        cutoff = ctx.now.timestamp() - float(ctx.loop_window_seconds)
        signature = _context_signature(ctx)
        sequence_count = 0
        prev_ts = None

        # Suppress loop detection when the same request stream is clearly
        # growing into a large expanding context, even before token explosion
        # fully qualifies.
        if _looks_like_token_context_growth(ctx):
            return []

        # Normalize ordering first because some repositories return descending
        # recent events while in-memory tests often preserve insertion order.
        ordered_events = sorted(ctx.recent_events, key=lambda event: event.created_at.timestamp(), reverse=True)

        # Walk newest to oldest and stop as soon as the rapid repeated sequence
        # breaks by signature, timing gap, or window boundary.
        for event in ordered_events:
            if event.provider != ctx.provider:
                continue
            event_ts = event.created_at.timestamp()
            if event_ts < cutoff:
                break
            event_signature = _signature(
                project_id=ctx.project_id,
                provider=event.provider,
                requested_model=event.requested_model,
                environment=event.environment,
                event=event,
            )
            if event_signature != signature:
                break
            if prev_ts is not None and (prev_ts - event_ts) > float(ctx.loop_max_gap_seconds):
                break
            
            # distinguish loop suspect from retry storm
            http_status = event.http_status or 0
            status = (event.status or "").strip().lower()

            is_failure = (
                (isinstance(http_status, int) and http_status >= 400)
                or status in {"error", "failed", "fail"}
                or bool(event.error_type)
            )

            if is_failure:
                continue

            sequence_count += 1
            prev_ts = event_ts

        # High request volume usually means parallel work rather than one step
        # feeding the next, so suppress loop detection in that case.
        if (
            ctx.current_requests_60s is not None
            and ctx.current_requests_60s >= int(ctx.loop_concurrency_threshold)
            and sequence_count < int(ctx.loop_count) * 2
        ):
            return []
        if sequence_count < ctx.loop_count:
            return []
        evidence: dict[str, object] = {
            "provider": ctx.provider,
            "requested_model": ctx.requested_model,
            "resolved_model": ctx.resolved_model,
            "environment": ctx.environment,
            "requests_60s": ctx.current_requests_60s,
            "tokens_60s": ctx.current_tokens_60s,
            "req_cap": ctx.req_cap,
            "tok_cap": ctx.tok_cap,
            "estimated_next_tokens": ctx.estimated_next_tokens,
            "signature": signature,
            "request_fingerprint": ctx.request_fingerprint,
            "window_seconds": ctx.loop_window_seconds,
            "sequence_count": sequence_count,
            "max_gap_seconds": ctx.loop_max_gap_seconds,
            "threshold_count": ctx.loop_count,
            "reason": "loop_suspect",
        }
        return [
            Signal(
                detector="loop_suspect",
                scope_provider=ctx.provider,
                fingerprint=f"{ctx.project_id}:{ctx.provider}:loop_suspect:{signature}",
                evidence=evidence,
                episode_window_seconds=ctx.loop_window_seconds,
                tags=_tags(ctx),
            )
        ]


def _signature(
    *,
    project_id: str,
    provider: str,
    requested_model: str | None,
    environment: str | None,
    event: Event | None,
) -> str:
    if event is None:
        return (
            f"{project_id}:{provider}:{normalized_model_name(requested_model) or 'na'}:"
            f"{environment or 'na'}:na:unknown:unknown"
        )
    endpoint = (event.request_endpoint or "na").strip()
    feature = (event.request_feature or "unknown").strip() or "unknown"
    fingerprint = (event.request_fingerprint or "unknown").strip() or "unknown"
    return (
        f"{project_id}:{provider}:{normalized_model_name(requested_model) or 'na'}:{environment or 'na'}:"
        f"{endpoint}:{feature}:{fingerprint}"
    )


def _context_signature(ctx: DetectionContext) -> str:
    endpoint = (ctx.request_endpoint or "na").strip()
    feature = (ctx.request_feature or "unknown").strip() or "unknown"
    fingerprint = (ctx.request_fingerprint or "unknown").strip() or "unknown"
    return (
        f"{ctx.project_id}:{ctx.provider}:{normalized_model_name(ctx.requested_model) or 'na'}:"
        f"{ctx.environment or 'na'}:{endpoint}:{feature}:{fingerprint}"
    )


def _tags(ctx: DetectionContext) -> dict[str, str]:
    tags: dict[str, str] = {}
    if ctx.requested_model:
        tags["requested_model"] = ctx.requested_model
    return tags


def _looks_like_token_context_growth(ctx: DetectionContext) -> bool:
    current_tokens = ctx.token_explosion_tokens
    if current_tokens is None and ctx.current_event is not None:
        current_tokens = ctx.current_event.token_explosion_tokens
    if current_tokens is None:
        current_tokens = ctx.estimated_next_tokens
    if current_tokens is None and ctx.current_event is not None:
        current_tokens = ctx.current_event.total_tokens
    if current_tokens is None:
        return False

    growth_floor = int(ctx.token_explosion_growth_min_tokens)
    current_tokens = max(int(current_tokens), 0)
    if current_tokens < growth_floor:
        return False

    previous_tokens = ctx.previous_estimated_tokens
    if previous_tokens is None:
        # A first already-large request context is not a stable loop signal.
        return True
    return current_tokens > max(int(previous_tokens), 0)
