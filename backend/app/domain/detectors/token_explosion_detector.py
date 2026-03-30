from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector
from app.domain.detectors.model_normalization import normalized_model_name
from app.domain.models.event import Event


class TokenExplosionDetector(Detector):
    # Detect unusually large request-context growth using a dedicated signal that
    # can be computed before a call and then echoed back on ingest, keeping
    # protect and observe aligned without conflating pattern detection with spend.
    def detect(self, ctx: DetectionContext) -> list[Signal]:
        token_explosion_tokens = ctx.token_explosion_tokens
        if token_explosion_tokens is None and ctx.current_event is not None:
            token_explosion_tokens = ctx.current_event.token_explosion_tokens
        if token_explosion_tokens is None:
            token_explosion_tokens = ctx.estimated_next_tokens
        if token_explosion_tokens is None and ctx.current_event is not None:
            token_explosion_tokens = max(int(ctx.current_event.total_tokens), 0)
        if token_explosion_tokens is None:
            return []

        ratio_threshold = None
        ratio_hit = False
        if ctx.tok_cap is not None and ctx.tok_cap > 0:
            ratio_threshold = float(ctx.tok_cap) * float(ctx.token_explosion_ratio)
            ratio_hit = float(token_explosion_tokens) >= ratio_threshold
        abs_hit = int(token_explosion_tokens) >= int(ctx.token_explosion_abs)

        # Growth detection compares the current request-context size with the last
        # matching request-context size so runaway accretion can surface before
        # absolute thresholds are crossed, but only once the request-context size
        # is already meaningfully large enough to avoid tiny-ratio noise.
        growth_hit = False
        growth_ratio = None
        # DetectionContext keeps the legacy field name for backward compatibility;
        # for token explosion it now carries the previous dedicated request-context signal.
        prev = ctx.previous_estimated_tokens
        if prev is not None and prev > 0:
            growth_ratio = float(token_explosion_tokens) / float(prev)
            growth_hit = (
                growth_ratio >= float(ctx.token_explosion_growth_ratio)
                and int(token_explosion_tokens) >= int(ctx.token_explosion_growth_min_tokens)
            )

        # Growth needs live current-window activity to mean "step-up inside an
        # active burst". With zero current traffic, the last persisted event may
        # be stale history from an earlier run, so suppress growth-only warns.
        if (ctx.current_requests_60s or 0) <= 0 or (ctx.current_tokens_60s or 0) <= 0:
            growth_hit = False

        # High request volume usually means concurrent requests rather than one step
        # feeding the next, so suppress growth-only interpretation in that case.
        if ctx.current_requests_60s is not None and ctx.current_requests_60s >= int(
            ctx.token_explosion_concurrency_threshold
        ):
            growth_hit = False

        if not (ratio_hit or abs_hit or growth_hit):
            return []
        evidence: dict[str, object] = {
            "provider": ctx.provider,
            "model": ctx.model,
            "environment": ctx.environment,
            "requests_60s": ctx.current_requests_60s,
            "tokens_60s": ctx.current_tokens_60s,
            "req_cap": ctx.req_cap,
            "tok_cap": ctx.tok_cap,
            "token_explosion_tokens": token_explosion_tokens,
            "previous_token_explosion_tokens": ctx.previous_estimated_tokens,
            "ratio_threshold_tokens": ratio_threshold,
            "absolute_threshold_tokens": ctx.token_explosion_abs,
            "growth_ratio": growth_ratio,
            "growth_threshold": ctx.token_explosion_growth_ratio,
            "growth_min_tokens": ctx.token_explosion_growth_min_tokens,
            "ratio_hit": ratio_hit,
            "absolute_hit": abs_hit,
            "growth_hit": growth_hit,
            "reason": "token_explosion",
        }
        return [
            Signal(
                detector="token_explosion",
                scope_provider=ctx.provider,
                fingerprint=f"{ctx.project_id}:{ctx.provider}:token_explosion",
                evidence=evidence,
                episode_window_seconds=60,
                tags=_tags(ctx),
            )
        ]


def _tags(ctx: DetectionContext) -> dict[str, str]:
    tags: dict[str, str] = {}
    if ctx.model:
        tags["model"] = ctx.model
    return tags


def resolve_previous_estimated_tokens(
    *,
    recent_events: list[Event],
    provider: str,
    model: str | None,
    current_event: Event | None = None,
) -> int | None:
    current_event_id = current_event.id if current_event is not None else None
    normalized_model = normalized_model_name(model)
    # Normalize ordering here so growth compares against the latest matching event
    # regardless of whether the caller hands us newest-first repository rows or
    # append-ordered test doubles.
    ordered_events = sorted(recent_events, key=lambda event: event.ts.timestamp(), reverse=True)
    for event in ordered_events:
        if event.provider != provider:
            continue
        if normalized_model_name(event.model) != normalized_model:
            continue
        if current_event_id is not None and event.id == current_event_id:
            continue
        if event.token_explosion_tokens is not None:
            return max(int(event.token_explosion_tokens), 0)
        return max(int(event.total_tokens), 0)
    return None
