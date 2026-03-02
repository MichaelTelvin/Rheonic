# Event builder helpers.
from datetime import datetime, timezone
from typing import Any

from rheonic.logger import get_logger

logger = get_logger(__name__)


def build_event(
    provider: str,
    model: str | None = None,
    environment: str = "dev",
    request: dict[str, Any] | None = None,
    response: dict[str, Any] | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    # Build backend ingest payload without project_id.
    return {
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model,
        "environment": environment,
        "request": request or {},
        "response": response or {},
    }


class EventBuilder:
    # Builds normalized usage events from provider responses.

    def build(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Build a backend-compatible event payload.
        try:
            return build_event(
                provider=str(payload.get("provider", "unknown")),
                model=payload.get("model") if isinstance(payload.get("model"), str) else None,
                environment=str(payload.get("environment", "dev")),
                request=payload.get("request") if isinstance(payload.get("request"), dict) else None,
                response=payload.get("response") if isinstance(payload.get("response"), dict) else None,
                ts=payload.get("ts") if isinstance(payload.get("ts"), str) else None,
            )
        except Exception:
            logger.exception("Event builder failed")
            raise
