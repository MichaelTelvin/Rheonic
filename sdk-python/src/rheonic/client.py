# SDK client with async fire-and-forget ingest queue.
import atexit
import json as json_lib
import os
import random
import threading
import time
from collections import deque
from typing import Any, Literal, Protocol, cast
from urllib import error, request
from uuid import uuid4

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

from rheonic.config import sdk_config
from rheonic.logger import (
    bind_trace_context,
    build_log_extra,
    configure_logging,
    generate_span_id,
    generate_trace_id,
    get_logger,
    get_span_id,
    get_trace_id,
    reset_trace_context,
)
from rheonic.protect_engine import ProtectEngine
from rheonic.token_estimator import prewarm_token_estimator

logger = get_logger(__name__)

OverflowPolicy = Literal["drop_oldest", "drop_newest"]

_default_client: "Client | None" = None


def _resolve_environment(explicit_environment: str | None) -> str:
    resolved = (
        explicit_environment
        or os.getenv("NODE_ENV")
        or os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("ENV")
        or sdk_config.default_environment
    )
    return str(resolved).strip() or sdk_config.default_environment


class HttpResponse(Protocol):
    # HTTP response contract used for retry logic.

    @property
    def status_code(self) -> int:
        # Numeric HTTP status code.
        ...


class HttpTransport(Protocol):
    # Small transport protocol for SDK HTTP clients.

    def post(
        self,
        url: str,
        json: dict[str, Any],
        headers: dict[str, str],
        timeout: float | None = None,
    ) -> HttpResponse:
        # Send one JSON request.
        ...

    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> HttpResponse:
        # Send one GET request.
        ...

    def close(self) -> None:
        # Close transport resources.
        ...


class _UrllibTransport:
    # stdlib HTTP transport fallback used when httpx is unavailable.

    def __init__(self, timeout_s: float = sdk_config.default_request_timeout_s) -> None:
        self._timeout_s = timeout_s

    def post(
        self,
        url: str,
        json: dict[str, Any],
        headers: dict[str, str],
        timeout: float | None = None,
    ) -> "_SimpleResponse":
        payload = request.Request(
            url=url,
            data=bytes(json_lib.dumps(json), encoding="utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(payload, timeout=timeout or self._timeout_s) as response:
                return _SimpleResponse(status_code=response.getcode())
        except error.HTTPError as exc:
            return _SimpleResponse(status_code=exc.code)

    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> "_SimpleResponse":
        payload = request.Request(
            url=url,
            headers=headers or {},
            method="GET",
        )
        try:
            with request.urlopen(payload, timeout=timeout or self._timeout_s) as response:
                return _SimpleResponse(status_code=response.getcode())
        except error.HTTPError as exc:
            return _SimpleResponse(status_code=exc.code)

    def close(self) -> None:
        return


class _SimpleResponse:
    # Small response object for urllib fallback transport.

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _HttpxTransport:
    # Adapter that exposes httpx.Client through the local transport protocol.

    def __init__(self, timeout_s: float) -> None:
        if httpx is None:  # pragma: no cover
            raise RuntimeError("httpx transport requested but httpx is unavailable")
        self._client = httpx.Client(timeout=timeout_s)

    def post(
        self,
        url: str,
        json: dict[str, Any],
        headers: dict[str, str],
        timeout: float | None = None,
    ) -> HttpResponse:
        return cast(HttpResponse, self._client.post(url, json=json, headers=headers, timeout=timeout))

    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> HttpResponse:
        return cast(HttpResponse, self._client.get(url, headers=headers, timeout=timeout))

    def close(self) -> None:
        self._client.close()


class Client:
    # Primary SDK client used by applications.

    def __init__(
        self,
        ingest_key: str,
        base_url: str | None = None,
        environment: str = sdk_config.default_environment,
        flush_interval_s: float = sdk_config.default_flush_interval_s,
        max_queue_size: int = sdk_config.default_max_queue_size,
        overflow_policy: OverflowPolicy = "drop_oldest",
        request_timeout_s: float = sdk_config.default_request_timeout_s,
        protect_fail_mode: str = sdk_config.default_protect_fail_mode,
        debug: bool = False,
        http_client: HttpTransport | None = None,
    ) -> None:
        # Initialize client queue, worker thread, and HTTP transport.
        try:
            resolved_environment = _resolve_environment(environment)
            env_debug = os.getenv("RHEONIC_DEBUG", "").lower() in {"1", "true", "yes"}
            self._debug_enabled = debug or env_debug
            configure_logging(
                level="DEBUG" if self._debug_enabled else None,
                environment=resolved_environment,
            )

            self.ingest_key = ingest_key
            resolved_base_url = base_url or os.getenv("RHEONIC_BASE_URL") or sdk_config.default_base_url
            self.base_url = resolved_base_url.rstrip("/")
            self.environment = resolved_environment
            self.flush_interval_s = flush_interval_s
            self.max_queue_size = max_queue_size
            self.overflow_policy = overflow_policy
            self.request_timeout_s = request_timeout_s
            self.protect_fail_mode = protect_fail_mode

            self._queue: deque[dict[str, Any]] = deque()
            self._lock = threading.Lock()
            self._stop_event = threading.Event()
            self._dropped = 0
            self._sent = 0
            self._failed = 0

            # Warm default/model-specific tokenizer state before the first protected call.
            prewarm_token_estimator()
            prewarm_model = os.getenv("RHEONIC_MODEL", "").strip() or None
            if prewarm_model is not None:
                prewarm_token_estimator(prewarm_model)

            if http_client is not None:
                self._http_client = http_client
            elif httpx is not None:
                self._http_client = _HttpxTransport(timeout_s=self.request_timeout_s)
            else:
                self._http_client = _UrllibTransport(timeout_s=self.request_timeout_s)
            self._protect_engine = ProtectEngine(
                base_url=self.base_url,
                ingest_key=self.ingest_key,
                environment=self.environment,
                request_timeout_s=self.request_timeout_s,
                fail_mode=self.protect_fail_mode,
                http_client=self._http_client,
                debug_logger=self.debug_log,
            )

            self._worker = threading.Thread(target=self._run_flush_loop, daemon=True)
            self._is_closed = False
            self._worker.start()
            self.warm_connections()
            atexit.register(self.close)
            logger.info(
                "SDK client initialized",
                extra=build_log_extra(
                    event="sdk_client_initialized",
                    trace_id=generate_trace_id(),
                    span_id=generate_span_id(),
                ),
            )
        except Exception:
            logger.exception("SDK client initialization failed", extra=build_log_extra(event="error"))
            raise

    def capture_event(self, event: dict[str, Any]) -> None:
        # Enqueue event without blocking provider call path.
        try:
            normalized = dict(event)
            normalized["environment"] = normalized.get("environment") or self.environment
            with self._lock:
                if len(self._queue) >= self.max_queue_size:
                    if self.overflow_policy == "drop_oldest":
                        self._queue.popleft()
                        self._dropped += 1
                    else:
                        self._dropped += 1
                        return
                self._queue.append(normalized)
        except Exception:
            logger.exception("capture_event enqueue failed", extra=build_log_extra(event="error"))
            return

    def capture_event_and_flush(self, event: dict[str, Any], timeout_s: float | None = None) -> None:
        self.capture_event(event)
        self.flush(timeout_s=timeout_s)

    def flush(self, timeout_s: float | None = None) -> None:
        # Best-effort flush queued events with optional time budget.
        deadline = time.monotonic() + timeout_s if timeout_s is not None else None
        try:
            while True:
                if deadline is not None and time.monotonic() >= deadline:
                    return
                with self._lock:
                    if not self._queue:
                        return
                    event = self._queue.popleft()
                self._send_event(event)
        except Exception:
            logger.exception("flush failed", extra=build_log_extra(event="error"))
            return

    def close(self) -> None:
        # Stop background worker and flush outstanding events.
        try:
            if self._is_closed:
                return
            self._is_closed = True
            self._stop_event.set()
            if self._worker.is_alive():
                self._worker.join(timeout=self.flush_interval_s)
            self.flush(timeout_s=sdk_config.default_flush_timeout_s)
            self._http_client.close()
        except Exception:
            logger.exception("client close failed", extra=build_log_extra(event="error"))
            return

    def stats(self) -> dict[str, int]:
        # Return queue and delivery counters.
        with self._lock:
            return {
                "queued": len(self._queue),
                "dropped": self._dropped,
                "sent": self._sent,
                "failed": self._failed,
            }

    def debug_log(self, message: str, **extra: object) -> None:
        # Emit SDK debug logs only when debug mode is enabled.
        if not self._debug_enabled:
            return
        if extra:
            rendered = " ".join(f"{key}={extra[key]}" for key in sorted(extra))
            logger.debug(
                message,
                extra=build_log_extra(event="sdk_debug", metadata={**extra, "rendered": rendered}),
            )
            return
        logger.debug(message, extra=build_log_extra(event="sdk_debug"))

    def preflight_protect_decision(self, context: dict[str, object]) -> dict[str, object]:
        # Evaluate protect decision for provider call preflight.
        try:
            return self._protect_engine.evaluate(
                {
                    **context,
                    "trace_id": context.get("trace_id") or get_trace_id() or None,
                    "span_id": context.get("span_id") or get_span_id() or None,
                }
            )
        except Exception:
            logger.exception("protect preflight failed unexpectedly", extra=build_log_extra(event="error"))
            trace_id = generate_trace_id()
            request_id = uuid4().hex
            if self.protect_fail_mode == "closed":
                return {
                    "decision": "block",
                    "reason": "fail_closed",
                    "trace_id": trace_id,
                    "request_id": request_id,
                }
            return {
                "decision": "allow",
                "reason": "decision_unavailable",
                "trace_id": trace_id,
                "request_id": request_id,
            }

    def warm_connections(self) -> None:
        # Best-effort warmup of the shared backend HTTP connection and protect runtime config.
        context_tokens = bind_trace_context(trace_id=generate_trace_id(), span_id=generate_span_id())
        try:
            response = self._http_client.get(
                f"{self.base_url}/health",
                headers={"X-Trace-ID": get_trace_id(), "X-Span-ID": generate_span_id()},
                timeout=min(self.request_timeout_s, 1.0),
            )
            status_code = int(getattr(response, "status_code", 0))
            self.debug_log("SDK connection warmup completed", status_code=status_code)
        except Exception:
            self.debug_log("SDK connection warmup failed")
        try:
            bootstrap_tokens = bind_trace_context(trace_id=generate_trace_id(), span_id=generate_span_id())
            try:
                self._protect_engine.bootstrap()
                self.debug_log("SDK protect config bootstrap completed")
            finally:
                reset_trace_context(bootstrap_tokens)
        except Exception:
            self.debug_log("SDK protect config bootstrap failed")
        finally:
            reset_trace_context(context_tokens)

    def instrument_openai(
        self,
        openai_client: Any,
        environment: str | None = None,
        endpoint: str | None = None,
        feature: str | None = None,
    ) -> Any:
        # Convenience wrapper that instruments an OpenAI client with this SDK client.
        from rheonic.providers.openai_adapter import instrument_openai

        return instrument_openai(
            openai_client,
            client=self,
            environment=environment,
            endpoint=endpoint,
            feature=feature,
        )

    def instrument_anthropic(
        self,
        anthropic_client: Any,
        environment: str | None = None,
        endpoint: str | None = None,
        feature: str | None = None,
    ) -> Any:
        # Convenience wrapper that instruments an Anthropic client with this SDK client.
        from rheonic.providers.anthropic_adapter import instrument_anthropic

        return instrument_anthropic(
            anthropic_client,
            client=self,
            environment=environment,
            endpoint=endpoint,
            feature=feature,
        )

    def instrument_google(
        self,
        google_client: Any,
        environment: str | None = None,
        endpoint: str | None = None,
        feature: str | None = None,
    ) -> Any:
        # Convenience wrapper that instruments a Google client with this SDK client.
        from rheonic.providers.google_adapter import instrument_google

        return instrument_google(
            google_client,
            client=self,
            environment=environment,
            endpoint=endpoint,
            feature=feature,
        )

    def _run_flush_loop(self) -> None:
        # Periodically flush queue until stopped.
        while not self._stop_event.wait(self.flush_interval_s):
            self.flush(timeout_s=sdk_config.default_flush_timeout_s)

    def _send_event(self, event: dict[str, Any]) -> None:
        # Send one event to backend ingest endpoint with one retry for transient failures.
        first_attempt_ok, should_retry = self._send_event_once(event)
        if first_attempt_ok:
            with self._lock:
                self._sent += 1
            return

        if not should_retry:
            with self._lock:
                self._failed += 1
            return

        time.sleep(random.uniform(sdk_config.retry_delay_min_s, sdk_config.retry_delay_max_s))
        second_attempt_ok, _ = self._send_event_once(event)
        with self._lock:
            if second_attempt_ok:
                self._sent += 1
            else:
                self._failed += 1

    def _send_event_once(self, event: dict[str, Any]) -> tuple[bool, bool]:
        # Send one event and classify retry behavior.
        context_tokens = bind_trace_context(trace_id=generate_trace_id())
        try:
            response = self._http_client.post(
                f"{self.base_url}/api/v1/events",
                json=event,
                headers={
                    "Content-Type": "application/json",
                    "X-Project-Ingest-Key": self.ingest_key,
                    "X-Trace-ID": get_trace_id(),
                    "X-Span-ID": generate_span_id(),
                },
            )
            status_code = int(getattr(response, "status_code", 0))
            if 200 <= status_code < 300:
                return True, False
            if status_code >= 500:
                return False, True
            return False, False
        except Exception as error:
            if self._debug_enabled:
                logger.debug(
                    "SDK send failed; retrying once",
                    extra=build_log_extra(event="http_retry", metadata={"error_message": str(error)}),
                )
            return False, True
        finally:
            reset_trace_context(context_tokens)


RheonicClient = Client


def create_client(
    ingest_key: str,
    base_url: str | None = None,
    environment: str = sdk_config.default_environment,
    flush_interval_s: float = sdk_config.default_flush_interval_s,
    max_queue_size: int = sdk_config.default_max_queue_size,
    overflow_policy: OverflowPolicy = "drop_oldest",
    request_timeout_s: float = sdk_config.default_request_timeout_s,
    protect_fail_mode: str = sdk_config.default_protect_fail_mode,
    debug: bool = False,
) -> Client:
    # Create and register default client used by module-level helpers.
    global _default_client
    if _default_client is not None:
        _default_client.close()
    _default_client = Client(
        ingest_key=ingest_key,
        base_url=base_url,
        environment=environment,
        flush_interval_s=flush_interval_s,
        max_queue_size=max_queue_size,
        overflow_policy=overflow_policy,
        request_timeout_s=request_timeout_s,
        protect_fail_mode=protect_fail_mode,
        debug=debug,
    )
    return _default_client


def get_default_client() -> Client | None:
    # Return default module-level client if configured.
    return _default_client


def capture_event(event: dict[str, Any]) -> None:
    # Enqueue event through default client when configured.
    client = get_default_client()
    if client is None:
        return
    client.capture_event(event)
