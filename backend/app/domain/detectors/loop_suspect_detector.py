from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector
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

        # Walk newest to oldest and stop as soon as the rapid repeated sequence
        # breaks by signature, timing gap, or window boundary.
        for event in reversed(ctx.recent_events):
            if event.provider != ctx.provider:
                continue
            event_ts = event.created_at.timestamp()
            if event_ts < cutoff:
                break
            event_signature = _signature(
                project_id=ctx.project_id,
                provider=event.provider,
                model=event.model,
                environment=event.environment,
                event=event,
            )
            if event_signature != signature:
                break
            if prev_ts is not None and (prev_ts - event_ts) > float(ctx.loop_max_gap_seconds):
                break
            sequence_count += 1
            prev_ts = event_ts

        # High request volume usually means parallel work rather than one step
        # feeding the next, so suppress loop detection in that case.
        if (
            ctx.current_requests_60s is not None
            and ctx.current_requests_60s >= int(ctx.loop_concurrency_threshold)
        ):
            return []
        if sequence_count < ctx.loop_count:
            return []
        evidence: dict[str, object] = {
            "provider": ctx.provider,
            "model": ctx.model,
            "environment": ctx.environment,
            "requests_60s": ctx.current_requests_60s,
            "tokens_60s": ctx.current_tokens_60s,
            "req_cap": ctx.req_cap,
            "tok_cap": ctx.tok_cap,
            "estimated_next_tokens": ctx.estimated_next_tokens,
            "signature": signature,
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
    model: str | None,
    environment: str | None,
    event: Event | None,
) -> str:
    if event is None:
        return f"{project_id}:{provider}:{model or 'na'}:{environment or 'na'}:na:unknown"
    endpoint = (event.request_endpoint or "na").strip()
    feature = (event.request_feature or "unknown").strip() or "unknown"
    return f"{project_id}:{provider}:{model or 'na'}:{environment or 'na'}:{endpoint}:{feature}"


def _context_signature(ctx: DetectionContext) -> str:
    endpoint = (ctx.request_endpoint or "na").strip()
    feature = (ctx.request_feature or "unknown").strip() or "unknown"
    return f"{ctx.project_id}:{ctx.provider}:{ctx.model or 'na'}:{ctx.environment or 'na'}:{endpoint}:{feature}"


def _tags(ctx: DetectionContext) -> dict[str, str]:
    tags: dict[str, str] = {}
    if ctx.model:
        tags["model"] = ctx.model
    return tags
