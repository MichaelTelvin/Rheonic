from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector


class TokenExplosionDetector(Detector):
    # Detect unusually large next-token estimate spikes.
    def detect(self, ctx: DetectionContext) -> list[Signal]:
        estimate = ctx.estimated_next_tokens
        if estimate is None and ctx.current_event is not None:
            estimate = max(int(ctx.current_event.total_tokens), 0)
        if estimate is None:
            return []

        ratio_threshold = None
        ratio_hit = False
        if ctx.tok_cap is not None and ctx.tok_cap > 0:
            ratio_threshold = float(ctx.tok_cap) * float(ctx.token_explosion_ratio)
            ratio_hit = float(estimate) >= ratio_threshold
        abs_hit = int(estimate) >= int(ctx.token_explosion_abs)
        if not (ratio_hit or abs_hit):
            return []
        evidence: dict[str, object] = {
            "provider": ctx.provider,
            "model": ctx.model,
            "environment": ctx.environment,
            "requests_60s": ctx.current_requests_60s,
            "tokens_60s": ctx.current_tokens_60s,
            "req_cap": ctx.req_cap,
            "tok_cap": ctx.tok_cap,
            "estimated_next_tokens": estimate,
            "ratio_threshold_tokens": ratio_threshold,
            "absolute_threshold_tokens": ctx.token_explosion_abs,
            "ratio_hit": ratio_hit,
            "absolute_hit": abs_hit,
            "reason": "token_explosion",
        }
        return [
            Signal(
                detector="token_explosion",
                scope_provider=ctx.provider,
                fingerprint=f"{ctx.project_id}:{ctx.provider}:token_explosion",
                evidence=evidence,
                tags=_tags(ctx),
            )
        ]


def _tags(ctx: DetectionContext) -> dict[str, str]:
    tags: dict[str, str] = {}
    if ctx.model:
        tags["model"] = ctx.model
    return tags
