from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector


class ReqSpikeDetector(Detector):
    # Emits request-spike signal when early absolute or gated relative thresholds are hit.

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        early_abs_hit, early_abs_evidence = ctx.gate.is_early_abs_spike()
        req_ratio = _ratio(ctx.current_requests_60s, ctx.baseline_req_60s)
        tok_ratio = _ratio(ctx.current_tokens_60s, ctx.baseline_tok_60s)
        req_delta = float(ctx.current_requests_60s) - float(ctx.baseline_req_60s)
        tok_delta = float(ctx.current_tokens_60s) - float(ctx.baseline_tok_60s)
        req_trigger = req_ratio >= ctx.req_spike_ratio_low and req_delta >= ctx.req_spike_delta_low
        tok_trigger = tok_ratio >= ctx.tok_spike_ratio_low and tok_delta >= ctx.tok_spike_delta_low

        # Preserve existing behavior: if tokens also spike, burn_spike path owns the incident.
        if tok_trigger:
            return []
        if early_abs_hit and early_abs_evidence.get("req_hit", False):
            return [_signal(ctx, req_ratio, tok_ratio, req_delta, tok_delta, True, early_abs_evidence)]
        if not ctx.gate.allow_baseline_relative_checks() or not req_trigger:
            return []
        return [_signal(ctx, req_ratio, tok_ratio, req_delta, tok_delta, False, early_abs_evidence)]


def _signal(
    ctx: DetectionContext,
    req_ratio: float,
    tok_ratio: float,
    req_delta: float,
    tok_delta: float,
    early_abs: bool,
    early_abs_evidence: dict[str, object],
) -> Signal:
    evidence = {
        "detector": "req_spike",
        "current_requests_60s": ctx.current_requests_60s,
        "current_tokens_60s": ctx.current_tokens_60s,
        "baseline_req_60s": ctx.baseline_req_60s,
        "baseline_tok_60s": ctx.baseline_tok_60s,
        "req_ratio": req_ratio,
        "tok_ratio": tok_ratio,
        "req_delta": req_delta,
        "tok_delta": tok_delta,
        "threshold_req_ratio_low": ctx.req_spike_ratio_low,
        "threshold_req_delta_low": ctx.req_spike_delta_low,
        "threshold_tok_ratio_low": ctx.tok_spike_ratio_low,
        "threshold_tok_delta_low": ctx.tok_spike_delta_low,
        "baseline_ready": ctx.gate.baseline_ready,
        "gate_reason": ctx.gate.reason,
        "baseline_windows": ctx.baseline_windows,
        "early_abs": early_abs,
        "early_abs_evidence": early_abs_evidence,
        "provider": ctx.provider,
        "model": ctx.model,
        "environment": ctx.environment,
    }
    tags: dict[str, str] = {}
    if ctx.feature:
        tags["feature"] = ctx.feature
    if ctx.model:
        tags["model"] = ctx.model
    return Signal(
        detector="req_spike",
        severity=_severity_for_ratio(max(req_ratio, tok_ratio)),
        scope_provider=ctx.provider,
        fingerprint=_build_signal_fingerprint(ctx, "req_spike"),
        evidence=evidence,
        tags=tags,
    )


def _ratio(current: int, baseline: float) -> float:
    return float(current) / max(float(baseline), 1.0)


def _severity_for_ratio(max_ratio: float) -> str:
    if max_ratio >= 10.0:
        return "high"
    if max_ratio >= 5.0:
        return "medium"
    return "low"


def _build_signal_fingerprint(ctx: DetectionContext, detector: str) -> str:
    feature = ctx.feature or "na"
    model = ctx.model or "na"
    return f"{ctx.project_id}:{ctx.provider}:{detector}:{feature}:{model}"
