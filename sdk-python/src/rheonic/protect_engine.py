# Protect mode preflight decision engine.
import sys
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from rheonic.config import sdk_config
from rheonic.logger import (
    bind_trace_context,
    generate_span_id,
    generate_trace_id,
    get_logger,
    get_span_id,
    get_trace_id,
    reset_trace_context,
)

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

logger = get_logger(__name__)


class RHEONICBlockedError(RuntimeError):
    # Raised when backend preflight blocks an outbound provider request.

    def __init__(
        self,
        reason: str,
        *,
        trace_id: str,
        request_id: str,
        blocked_until: str | None = None,
        retry_after_seconds: int | None = None,
        snapshot: dict[str, object] | None = None,
    ) -> None:
        super().__init__(f"Request blocked by Rheonic: {reason}")
        self.reason = reason
        self.trace_id = trace_id
        self.request_id = request_id
        self.blocked_until = blocked_until
        self.retry_after_seconds = retry_after_seconds
        self.snapshot = snapshot


class RHEONICValidationError(Exception):
    # Raised when provider and model combination is invalid for SDK instrumentation.

    pass


class ProtectEngine:
    # Evaluates always-on protect preflight decisions against backend endpoint.

    def __init__(
        self,
        base_url: str,
        ingest_key: str,
        environment: str,
        request_timeout_s: float,
        fail_mode: str = sdk_config.default_protect_fail_mode,
        decision_timeout_ms: int = sdk_config.internal_protect_decision_timeout_ms,
        http_client: object | None = None,
        debug_logger: Any | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._ingest_key = ingest_key
        self._environment = environment
        self._request_timeout_s = request_timeout_s
        self._fail_mode = fail_mode if fail_mode in {"open", "closed"} else "open"
        self._decision_timeout_ms = (
            int(decision_timeout_ms) if decision_timeout_ms > 0 else sdk_config.internal_protect_decision_timeout_ms
        )
        self._http_client = http_client
        self._debug_logger = debug_logger
        self._cooldown_until_ms: int | None = None
        self._cooldown_reason: str | None = None

    def evaluate(self, context: dict[str, object]) -> dict[str, object]:
        # Return allow/clamp/block decision from backend with fail-mode fallback.
        request_id = uuid4().hex
        trace_id_value = context.get("trace_id")
        span_id_value = context.get("span_id")
        trace_id = str(trace_id_value).strip() if isinstance(trace_id_value, str) else ""
        span_id = str(span_id_value).strip() if isinstance(span_id_value, str) else ""
        trace_id = trace_id or generate_trace_id()
        span_id = span_id or generate_span_id()
        now_ms = int(time.time() * 1000)
        if self._cooldown_until_ms is not None and now_ms < self._cooldown_until_ms:
            context_tokens = bind_trace_context(trace_id=trace_id, span_id=span_id)
            try:
                self._debug(
                    "Protect preflight blocked locally from cached cooldown",
                    provider=context.get("provider"),
                    decision="block",
                    reason=self._cooldown_reason or "cooldown_active",
                )
                return {
                    "decision": "block",
                    "reason": self._cooldown_reason or "cooldown_active",
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "blocked_until": _format_blocked_until_ms(self._cooldown_until_ms),
                    "retry_after_seconds": _to_retry_after_seconds(self._cooldown_until_ms, now_ms),
                }
            finally:
                reset_trace_context(context_tokens)

        timeout_s = max(self._decision_timeout_ms, 1) / 1000.0
        started_at = time.perf_counter()
        context_tokens = bind_trace_context(trace_id=trace_id, span_id=span_id)
        try:
            response = self._post_with_timeout(
                f"{self._base_url}/api/v1/protect/decision",
                json=context,
                headers={
                    "Content-Type": "application/json",
                    "X-Project-Ingest-Key": self._ingest_key,
                    "X-Trace-ID": get_trace_id(),
                    "X-Span-ID": get_span_id(),
                    "X-Rheonic-Protect-Request-Id": request_id,
                },
                timeout_s=timeout_s,
            )
            status_code = int(getattr(response, "status_code", 0))
            if status_code < 200 or status_code >= 300:
                self._debug(
                    "Protect preflight returned non-success status",
                    provider=context.get("provider"),
                    status_code=status_code,
                    latency_ms=int((time.perf_counter() - started_at) * 1000),
                )
                self._report_decision_unavailable_fire_and_forget(
                    provider=str(context.get("provider")) if isinstance(context.get("provider"), str) else None,
                    model=str(context.get("model")) if isinstance(context.get("model"), str) else None,
                    request_id=request_id,
                    trace_id=get_trace_id(),
                )
                return self._fallback_decision(trace_id=trace_id, request_id=request_id)
            payload = self._parse_json_payload(response)
            decision = str(payload.get("decision") or "allow")
            reason = str(payload.get("reason") or "ok")
            fail_mode = str(payload.get("fail_mode") or self._fail_mode)
            if fail_mode in {"open", "closed"}:
                self._fail_mode = fail_mode
            decision_timeout = payload.get("protect_decision_timeout_ms")
            if isinstance(decision_timeout, int) and decision_timeout > 0:
                self._decision_timeout_ms = decision_timeout
            blocked_until_ms = _parse_blocked_until_ms(payload.get("blocked_until"))
            if blocked_until_ms is not None and blocked_until_ms > int(time.time() * 1000):
                self._cooldown_until_ms = blocked_until_ms
                self._cooldown_reason = "cooldown_active"
            elif self._cooldown_until_ms is not None and int(time.time() * 1000) >= self._cooldown_until_ms:
                self._cooldown_until_ms = None
                self._cooldown_reason = None
            if decision not in {"allow", "clamp", "block"}:
                decision = "allow"
            result: dict[str, object] = {"decision": decision, "reason": reason}
            result["trace_id"] = trace_id
            result["request_id"] = request_id
            blocked_until_value = payload.get("blocked_until")
            if isinstance(blocked_until_value, str) and blocked_until_value.strip():
                result["blocked_until"] = blocked_until_value
            retry_after_seconds = payload.get("retry_after_seconds")
            if isinstance(retry_after_seconds, int) and retry_after_seconds >= 0:
                result["retry_after_seconds"] = retry_after_seconds
            apply_clamp_enabled = payload.get("apply_clamp_enabled")
            if isinstance(apply_clamp_enabled, bool):
                result["apply_clamp_enabled"] = apply_clamp_enabled
            snapshot_payload = payload.get("snapshot")
            if isinstance(snapshot_payload, dict):
                result["snapshot"] = snapshot_payload
            clamp_payload = payload.get("clamp")
            if isinstance(clamp_payload, dict):
                recommended = clamp_payload.get("recommended_max_output_tokens")
                applied = clamp_payload.get("applied")
                if isinstance(recommended, int) and recommended > 0:
                    result["clamp"] = {
                        "recommended_max_output_tokens": recommended,
                        "applied": bool(applied) if isinstance(applied, bool) else False,
                    }
            self._debug(
                "Protect preflight completed",
                provider=context.get("provider"),
                decision=decision,
                reason=reason,
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                timeout_ms=self._decision_timeout_ms,
            )
            return result
        except Exception:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            if self._is_timeout_error():
                provider = context.get("provider")
                self._debug(
                    "Protect preflight timed out",
                    provider=provider,
                    latency_ms=latency_ms,
                    timeout_ms=self._decision_timeout_ms,
                )
                self._report_decision_timeout_fire_and_forget(
                    provider=str(provider) if isinstance(provider, str) else None,
                    model=str(context.get("model")) if isinstance(context.get("model"), str) else None,
                    request_id=request_id,
                    trace_id=get_trace_id(),
                )
            else:
                provider = context.get("provider")
                self._debug(
                    "Protect preflight failed",
                    provider=provider,
                    latency_ms=latency_ms,
                    error_type=type(sys.exc_info()[1]).__name__ if sys.exc_info()[1] is not None else "unknown",
                )
                self._report_decision_unavailable_fire_and_forget(
                    provider=str(provider) if isinstance(provider, str) else None,
                    model=str(context.get("model")) if isinstance(context.get("model"), str) else None,
                    request_id=request_id,
                    trace_id=get_trace_id(),
                )
            return self._fallback_decision(trace_id=trace_id, request_id=request_id)
        finally:
            reset_trace_context(context_tokens)

    def bootstrap(self) -> None:
        # Load runtime protect config so timeout fallback matches server-side project mode.
        try:
            response = self._get_with_timeout(
                f"{self._base_url}/api/v1/protect/config",
                headers={
                    "X-Project-Ingest-Key": self._ingest_key,
                    "X-Trace-ID": generate_trace_id(),
                    "X-Span-ID": generate_span_id(),
                },
                timeout_s=max(self._request_timeout_s, 0.1),
            )
            status_code = int(getattr(response, "status_code", 0))
            if status_code < 200 or status_code >= 300:
                return
            payload = self._parse_json_payload(response)
            fail_mode = str(payload.get("protect_fail_mode") or self._fail_mode)
            if fail_mode in {"open", "closed"}:
                self._fail_mode = fail_mode
            decision_timeout = payload.get("protect_decision_timeout_ms")
            if isinstance(decision_timeout, int) and decision_timeout > 0:
                self._decision_timeout_ms = decision_timeout
        except Exception:
            return

    def _post_with_timeout(
        self,
        url: str,
        json: dict[str, object],
        headers: dict[str, str],
        timeout_s: float,
    ) -> object:
        # Call transport with timeout when supported.
        if self._http_client is None:
            raise RuntimeError("protect engine missing HTTP client")
        post = getattr(self._http_client, "post")
        try:
            return post(url, json=json, headers=headers, timeout=timeout_s)
        except TypeError:
            try:
                return post(url, json=json, headers=headers, timeout_s=timeout_s)
            except TypeError:
                return post(url, json=json, headers=headers)

    def _get_with_timeout(
        self,
        url: str,
        headers: dict[str, str],
        timeout_s: float,
    ) -> object:
        # Call transport GET with timeout when supported.
        if self._http_client is None:
            raise RuntimeError("protect engine missing HTTP client")
        get = getattr(self._http_client, "get")
        try:
            return get(url, headers=headers, timeout=timeout_s)
        except TypeError:
            try:
                return get(url, headers=headers, timeout_s=timeout_s)
            except TypeError:
                return get(url, headers=headers)

    def _parse_json_payload(self, response: object) -> dict[str, Any]:
        # Parse JSON response payload when supported by transport.
        json_loader = getattr(response, "json", None)
        if callable(json_loader):
            payload = json_loader()
            if isinstance(payload, dict):
                return payload
        return {}

    def _fallback_decision(self, *, trace_id: str, request_id: str) -> dict[str, object]:
        # Apply fail-open/fail-closed behavior when decision call fails.
        if self._fail_mode == "closed":
            return {"decision": "block", "reason": "fail_closed", "trace_id": trace_id, "request_id": request_id}
        return {"decision": "allow", "reason": "decision_unavailable", "trace_id": trace_id, "request_id": request_id}

    def _is_timeout_error(self) -> bool:
        # Identify timeout failures from common SDK transports.
        exc = sys.exc_info()[1]
        if isinstance(exc, TimeoutError):
            return True
        if httpx is not None and isinstance(exc, httpx.TimeoutException):
            return True
        return False

    def _report_decision_timeout_fire_and_forget(
        self, provider: str | None, model: str | None, request_id: str, trace_id: str | None
    ) -> None:
        # Report decision timeout without blocking caller flow.
        try:
            self._post_with_timeout(
                f"{self._base_url}/api/v1/protect/decision-timeout",
                json={"environment": self._environment, "provider": provider, "model": model, "request_id": request_id},
                headers={
                    "Content-Type": "application/json",
                    "X-Project-Ingest-Key": self._ingest_key,
                    "X-Trace-ID": trace_id or generate_trace_id(),
                    "X-Span-ID": generate_span_id(),
                    "X-Rheonic-Protect-Request-Id": request_id,
                },
                timeout_s=max(self._request_timeout_s, sdk_config.default_protect_report_timeout_min_s),
            )
        except Exception:
            return

    def _report_decision_unavailable_fire_and_forget(
        self, provider: str | None, model: str | None, request_id: str, trace_id: str | None
    ) -> None:
        # Report non-timeout preflight fallback without blocking caller flow.
        try:
            self._post_with_timeout(
                f"{self._base_url}/api/v1/protect/decision-unavailable",
                json={"environment": self._environment, "provider": provider, "model": model, "request_id": request_id},
                headers={
                    "Content-Type": "application/json",
                    "X-Project-Ingest-Key": self._ingest_key,
                    "X-Trace-ID": trace_id or generate_trace_id(),
                    "X-Span-ID": generate_span_id(),
                    "X-Rheonic-Protect-Request-Id": request_id,
                },
                timeout_s=max(self._request_timeout_s, sdk_config.default_protect_report_timeout_min_s),
            )
        except Exception:
            return

    def _debug(self, message: str, **extra: object) -> None:
        if callable(self._debug_logger):
            try:
                self._debug_logger(message, **extra)
                return
            except Exception:
                logger.exception("Protect engine debug logger failed")
        logger.debug(message, extra=extra or None)


def _parse_blocked_until_ms(value: object) -> int | None:
    # Parse blocked-until timestamp from decision payload.
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _format_blocked_until_ms(value: int | None) -> str | None:
    if value is None or value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).isoformat()


def _to_retry_after_seconds(blocked_until_ms: int | None, now_ms: int) -> int | None:
    if blocked_until_ms is None or blocked_until_ms <= now_ms:
        return None
    return max(0, int((blocked_until_ms - now_ms + 999) / 1000))
