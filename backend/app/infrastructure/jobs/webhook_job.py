# Background job for project webhook deliveries.
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException

from app.config import Settings, app_config
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.logger import get_logger
from app.security.webhook_urls import ensure_webhook_url_is_safe

logger = get_logger(__name__)

def _format_error_message(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        status = exc.response.status_code
        return f"HTTP {status}"[: app_config.webhook_max_error_chars]
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, str):
            return detail[: app_config.webhook_max_error_chars]
        return str(detail)[: app_config.webhook_max_error_chars]
    return str(exc).splitlines()[0][: app_config.webhook_max_error_chars]


def send_project_webhook(
    project_id: str,
    payload: dict[str, object],
    event_type: str,
    override_url: str | None = None,
    override_secret: str | None = None,
    force_send: bool = False,
) -> None:
    # Deliver one webhook and persist latest status on project.
    settings = Settings()
    repository = ProjectRepositoryImpl(session_factory=DatabaseSessionFactory())
    project = repository.get_project(project_id)
    if project is None:
        return

    if not force_send and (not project.webhook_enabled or not project.webhook_url):
        return

    target_url = override_url or project.webhook_url
    if not target_url:
        return

    body_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-RHEONIC-Event-Type": event_type,
    }
    signing_secret = override_secret if override_secret is not None else project.webhook_secret
    if signing_secret:
        digest = hmac.new(
            signing_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        headers["X-RHEONIC-Signature"] = f"sha256={digest}"

    now = datetime.now(timezone.utc)
    try:
        ensure_webhook_url_is_safe(target_url, settings=settings)
        timeout = httpx.Timeout(
            connect=app_config.webhook_timeout_connect_seconds,
            read=app_config.webhook_timeout_read_seconds,
            write=app_config.webhook_timeout_write_seconds,
            pool=app_config.webhook_timeout_pool_seconds,
        )
        with httpx.Client(timeout=timeout) as client:
            response = client.post(target_url, content=body_bytes, headers=headers)
            response.raise_for_status()
        repository.update_project_webhook_delivery_status(
            project_id=project_id,
            status="success",
            at=now,
            error=None,
        )
    except Exception as exc:
        message = _format_error_message(exc)
        repository.update_project_webhook_delivery_status(
            project_id=project_id,
            status="failed",
            at=now,
            error=message,
        )
        if event_type == "webhook.test":
            logger.exception(
                "Webhook test delivery failed",
                extra={"project_id": project_id, "error": message},
            )
            return
        logger.exception("Webhook delivery failed", extra={"project_id": project_id, "event_type": event_type})
        raise
