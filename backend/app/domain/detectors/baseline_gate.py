from app.domain.detectors.contracts import BaselineGateDecision


class BaselineGate:
    # Reusable warm-up gate for baseline-relative anomaly checks.

    def __init__(
        self,
        *,
        min_windows: int,
        min_baseline_req: float,
        min_baseline_tok: float,
        early_abs_req_60s: int,
        early_abs_tok_60s: int,
    ) -> None:
        self._min_windows = min_windows
        self._min_baseline_req = min_baseline_req
        self._min_baseline_tok = min_baseline_tok
        self._early_abs_req_60s = early_abs_req_60s
        self._early_abs_tok_60s = early_abs_tok_60s

    def evaluate(
        self,
        *,
        current_requests_60s: int,
        current_tokens_60s: int,
        baseline_req_60s: float,
        baseline_tok_60s: float,
        baseline_windows: int,
    ) -> BaselineGateDecision:
        baseline_ready = (
            baseline_windows >= self._min_windows
            and (
                baseline_req_60s >= self._min_baseline_req
                or baseline_tok_60s >= self._min_baseline_tok
            )
        )
        reason = "ready" if baseline_ready else "warmup"
        return BaselineGateDecision(
            baseline_ready=baseline_ready,
            reason=reason,
            baseline_windows=baseline_windows,
            min_windows=self._min_windows,
            min_baseline_req=self._min_baseline_req,
            min_baseline_tok=self._min_baseline_tok,
            current_requests_60s=current_requests_60s,
            current_tokens_60s=current_tokens_60s,
            baseline_req_60s=baseline_req_60s,
            baseline_tok_60s=baseline_tok_60s,
            early_abs_req_60s=self._early_abs_req_60s,
            early_abs_tok_60s=self._early_abs_tok_60s,
        )
