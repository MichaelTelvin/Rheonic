# Background job for project webhook deliveries.
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

import httpx

from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.logger import get_logger

logger = get_logger(__name__)

_MAX_ERROR_CHARS = 240


def send_project_webhook(project_id: str, payload: dict[str, object], event_type: str) -> None:
    # Deliver one webhook and persist latest status on project.
    repository = ProjectRepositoryImpl(session_factory=DatabaseSessionFactory())
    project = repository.get_project(project_id)
    if project is None:
        return
    if not project.webhook_enabled or not project.webhook_url:
        return

    body_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-LLMTBG-Event-Type": event_type,
    }
    if project.webhook_secret:
        digest = hmac.new(
            project.webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        headers["X-LLMTBG-Signature"] = f"sha256={digest}"

    now = datetime.now(timezone.utc)
    try:
        timeout = httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=5.0)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(project.webhook_url, content=body_bytes, headers=headers)
            response.raise_for_status()
        repository.update_project_webhook_delivery_status(
            project_id=project_id,
            status="success",
            at=now,
            error=None,
        )
    except Exception as exc:
        message = str(exc)[:_MAX_ERROR_CHARS]
        repository.update_project_webhook_delivery_status(
            project_id=project_id,
            status="failed",
            at=now,
            error=message,
        )
        logger.exception("Webhook delivery failed", extra={"project_id": project_id, "event_type": event_type})
        raise
