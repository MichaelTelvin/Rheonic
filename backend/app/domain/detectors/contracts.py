from dataclasses import dataclass, field
from typing import Literal


Severity = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Signal:
    # Detector output consumed by incident manager.
    detector: str
    severity: Severity
    scope_provider: str
    fingerprint: str
    evidence: dict[str, object]
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BaselineGateDecision:
    # Warm-up decision for baseline-relative checks.
    baseline_ready: bool
    reason: str
    baseline_windows: int
    min_windows: int
    min_baseline_req: float
    min_baseline_tok: float
    current_requests_60s: int
    current_tokens_60s: int
    baseline_req_60s: float
    baseline_tok_60s: float
    early_abs_req_60s: int
    early_abs_tok_60s: int

    def allow_baseline_relative_checks(self) -> bool:
        return self.baseline_ready

    def is_early_abs_spike(self) -> tuple[bool, dict[str, object]]:
        req_hit = self.current_requests_60s >= self.early_abs_req_60s
        tok_hit = self.current_tokens_60s >= self.early_abs_tok_60s
        return (
            req_hit or tok_hit,
            {
                "req_hit": req_hit,
                "tok_hit": tok_hit,
                "early_abs_req_60s": self.early_abs_req_60s,
                "early_abs_tok_60s": self.early_abs_tok_60s,
            },
        )


@dataclass(frozen=True)
class DetectionContext:
    # Shared detector input for one ingest evaluation.
    project_id: str
    provider: str
    model: str | None
    feature: str | None
    environment: str | None
    current_requests_60s: int
    current_tokens_60s: int
    baseline_req_60s: float
    baseline_tok_60s: float
    baseline_windows: int
    gate: BaselineGateDecision
    req_spike_ratio_low: float
    req_spike_delta_low: float
    tok_spike_ratio_low: float
    tok_spike_delta_low: float
