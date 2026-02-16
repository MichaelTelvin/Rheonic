# SDK client with async fire-and-forget ingest queue.
import atexit
import threading
import time
from collections import deque
from typing import Any

import httpx

from llmtokenburnguard.logger import configure_logging, get_logger

logger = get_logger(__name__)

_DEFAULT_BASE_URL = "http://localhost:8000"
_DEFAULT_ENVIRONMENT = "dev"
_DEFAULT_FLUSH_INTERVAL_S = 1.0
_DEFAULT_MAX_QUEUE_SIZE = 1000
_DEFAULT_FLUSH_TIMEOUT_S = 0.5

_default_client: "Client | None" = None


class Client:
    # Primary SDK client used by applications.

    def __init__(
        self,
        ingest_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        environment: str = _DEFAULT_ENVIRONMENT,
        flush_interval_s: float = _DEFAULT_FLUSH_INTERVAL_S,
        max_queue_size: int = _DEFAULT_MAX_QUEUE_SIZE,
        http_client: httpx.Client | None = None,
    ) -> None:
        # Initialize client queue, worker thread, and HTTP transport.
        try:
            configure_logging()
            self.ingest_key = ingest_key
            self.base_url = base_url.rstrip("/")
            self.environment = environment
            self.flush_interval_s = flush_interval_s
            self.max_queue_size = max_queue_size
            self._queue: deque[dict[str, Any]] = deque()
            self._lock = threading.Lock()
            self._stop_event = threading.Event()
            self._http_client = http_client or httpx.Client(timeout=1.0)
            self._worker = threading.Thread(target=self._run_flush_loop, daemon=True)
            self._worker.start()
            atexit.register(self.flush)
            logger.info("SDK client initialized")
        except Exception:
            logger.exception("SDK client initialization failed")
            raise

    def capture_event(self, event: dict[str, Any]) -> None:
        # Enqueue event without blocking provider call path.
        try:
            normalized = dict(event)
            normalized["environment"] = normalized.get("environment") or self.environment
            with self._lock:
                if len(self._queue) >= self.max_queue_size:
                    return
                self._queue.append(normalized)
        except Exception:
            logger.exception("capture_event enqueue failed")
            return

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
            logger.exception("flush failed")
            return

    def close(self) -> None:
        # Stop background worker and flush outstanding events.
        try:
            self._stop_event.set()
            if self._worker.is_alive():
                self._worker.join(timeout=self.flush_interval_s)
            self.flush(timeout_s=_DEFAULT_FLUSH_TIMEOUT_S)
        except Exception:
            logger.exception("client close failed")
            return

    def _run_flush_loop(self) -> None:
        # Periodically flush queue until stopped.
        while not self._stop_event.wait(self.flush_interval_s):
            self.flush(timeout_s=_DEFAULT_FLUSH_TIMEOUT_S)

    def _send_event(self, event: dict[str, Any]) -> None:
        # Send one event to backend ingest endpoint.
        try:
            self._http_client.post(
                f"{self.base_url}/api/v1/events",
                json=event,
                headers={
                    "Content-Type": "application/json",
                    "X-Project-Ingest-Key": self.ingest_key,
                },
            )
        except Exception:
            return


LLMTokenBurnGuardClient = Client


def create_client(
    ingest_key: str,
    base_url: str = _DEFAULT_BASE_URL,
    environment: str = _DEFAULT_ENVIRONMENT,
    flush_interval_s: float = _DEFAULT_FLUSH_INTERVAL_S,
    max_queue_size: int = _DEFAULT_MAX_QUEUE_SIZE,
) -> Client:
    # Create and register default client used by module-level helpers.
    global _default_client
    _default_client = Client(
        ingest_key=ingest_key,
        base_url=base_url,
        environment=environment,
        flush_interval_s=flush_interval_s,
        max_queue_size=max_queue_size,
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
