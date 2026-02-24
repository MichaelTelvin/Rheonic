# Protect mode preflight decision engine.
import sys
import time
from datetime import datetime, timezone
from typing import Any

from llmtokenburnguard.config import sdk_config
from llmtokenburnguard.logger import get_logger

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

logger = get_logger(__name__)


class LLMTBGBlockedError(RuntimeError):
    # Raised when backend preflight blocks an outbound provider request.

    def __init__(self, reason: str) -> None:
        super().__init__(f"Request blocked by LLMTokenBurnGuard: {reason}")
        self.reason = reason


class LLMTBGValidationError(Exception):
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
        decision_timeout_ms: int = sdk_config.default_protect_decision_timeout_ms,
        http_client: object | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._ingest_key = ingest_key
        self._environment = environment
        self._request_timeout_s = request_timeout_s
        self._fail_mode = fail_mode if fail_mode in {"open", "closed"} else "open"
        self._decision_timeout_ms = (
            int(decision_timeout_ms)
            if decision_timeout_ms > 0
            else sdk_config.default_protect_decision_timeout_ms
        )
        self._http_client = http_client
        self._cooldown_until_ms: int | None = None
        self._cooldown_reason: str | None = None

    def evaluate(self, context: dict[str, object]) -> dict[str, object]:
        # Return allow/warn/block decision from backend with fail-mode fallback.
        now_ms = int(time.time() * 1000)
        if self._cooldown_until_ms is not None and now_ms < self._cooldown_until_ms:
            return {"decision": "block", "reason": self._cooldown_reason or "cooldown_active"}

        timeout_s = max(self._decision_timeout_ms, 1) / 1000.0
        try:
            
            response = self._post_with_timeout(
                f"{self._base_url}/api/v1/protect/decision",
                json=context,
                headers={
                    "Content-Type": "application/json",
                    "X-Project-Ingest-Key": self._ingest_key,
                },
                timeout_s=timeout_s,
            )
            status_code = int(getattr(response, "status_code", 0))
            if status_code < 200 or status_code >= 300:
                return self._fallback_decision()
            
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
            if decision not in {"allow", "warn", "block"}:
                decision = "allow"
            return {"decision": decision, "reason": reason}
        except Exception:
            if self._is_timeout_error():
                self._report_decision_timeout_fire_and_forget()
            return self._fallback_decision()

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

    def _parse_json_payload(self, response: object) -> dict[str, Any]:
        # Parse JSON response payload when supported by transport.
        json_loader = getattr(response, "json", None)
        if callable(json_loader):
            payload = json_loader()
            if isinstance(payload, dict):
                return payload
        return {}

    def _fallback_decision(self) -> dict[str, object]:
        # Apply fail-open/fail-closed behavior when decision call fails.
        if self._fail_mode == "closed":
            return {"decision": "block", "reason": "decision_unavailable"}
        return {"decision": "allow", "reason": "decision_unavailable"}

    def _is_timeout_error(self) -> bool:
        # Identify timeout failures from common SDK transports.
        exc = sys.exc_info()[1]
        if isinstance(exc, TimeoutError):
            return True
        if httpx is not None and isinstance(exc, httpx.TimeoutException):
            return True
        return False

    def _report_decision_timeout_fire_and_forget(self) -> None:
        # Report decision timeout without blocking caller flow.
        def _send() -> None:
            try:
                self._post_with_timeout(
                    f"{self._base_url}/api/v1/protect/decision-timeout",
                    json={"environment": self._environment},
                    headers={
                        "Content-Type": "application/json",
                        "X-Project-Ingest-Key": self._ingest_key,
                    },
                    timeout_s=max(self._request_timeout_s, sdk_config.default_protect_report_timeout_min_s),
                )
            except Exception:
                return

        import threading

        threading.Thread(target=_send, daemon=True).start()


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
