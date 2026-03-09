from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import httpx
from redis import Redis
from rq import Queue

from app.application.email_templates.registry import render_template
from app.config import Settings, app_config
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.infrastructure.db.repositories.transport_outbox_repository_impl import TransportOutboxRepositoryImpl
from app.infrastructure.email.null_email_transport import EmailProviderNotConfiguredError, NullEmailTransport
from app.logger import get_logger
from app.security.webhook_urls import ensure_webhook_url_is_safe

logger = get_logger(__name__)


def enqueue_outbox_delivery(outbox_id: str) -> None:
    settings = Settings()
    queue = Queue(settings.rq_queue_name, connection=Redis.from_url(settings.redis_url))
    queue.enqueue(process_outbox_delivery, kwargs={"outbox_id": outbox_id})


def process_outbox_delivery(outbox_id: str) -> None:
    settings = Settings()
    now = datetime.now(timezone.utc)
    repository = TransportOutboxRepositoryImpl(session_factory=DatabaseSessionFactory())
    outbox = repository.claim_for_send(outbox_id=outbox_id, now=now)
    if outbox is None:
        logger.info("Outbox delivery skipped; row unavailable [outbox_id=%s]", outbox_id, extra={"outbox_id": outbox_id})
        return

    logger.info(
        "Outbox delivery claimed [outbox_id=%s kind=%s event_type=%s project_id=%s attempts=%s max_attempts=%s]",
        outbox.id,
        outbox.kind,
        outbox.event_type,
        outbox.project_id,
        int(outbox.attempts),
        int(outbox.max_attempts),
        extra={
            "outbox_id": outbox.id,
            "kind": outbox.kind,
            "event_type": outbox.event_type,
            "project_id": outbox.project_id,
            "attempts": int(outbox.attempts),
            "max_attempts": int(outbox.max_attempts),
        },
    )
    try:
        if outbox.kind == "webhook":
            _deliver_webhook(outbox_id=outbox.id)
        elif outbox.kind == "email":
            _deliver_email(outbox_id=outbox.id, settings=settings)
        else:
            raise RuntimeError(f"unsupported transport kind: {outbox.kind}")
        repository.mark_delivered(outbox_id=outbox.id, now=datetime.now(timezone.utc))
        logger.info(
            "Outbox delivery succeeded [outbox_id=%s kind=%s event_type=%s project_id=%s]",
            outbox.id,
            outbox.kind,
            outbox.event_type,
            outbox.project_id,
            extra={
                "outbox_id": outbox.id,
                "kind": outbox.kind,
                "event_type": outbox.event_type,
                "project_id": outbox.project_id,
            },
        )
    except Exception as exc:
        attempts = max(int(outbox.attempts), 1)
        delay_seconds = _retry_delay_seconds(kind=outbox.kind, attempt_number=attempts)
        dead = attempts >= int(outbox.max_attempts) or delay_seconds is None
        next_attempt_at = None if dead else datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        code, message = _error_details(exc)
        repository.mark_failed(
            outbox_id=outbox.id,
            now=datetime.now(timezone.utc),
            error_code=code,
            error_message=message,
            next_attempt_at=next_attempt_at,
            dead=dead,
        )
        logger.warning(
            "Outbox delivery failed [outbox_id=%s kind=%s event_type=%s project_id=%s attempts=%s max_attempts=%s error_code=%s dead=%s retry_delay_seconds=%s]",
            outbox.id,
            outbox.kind,
            outbox.event_type,
            outbox.project_id,
            attempts,
            int(outbox.max_attempts),
            code,
            dead,
            delay_seconds,
            extra={
                "outbox_id": outbox.id,
                "kind": outbox.kind,
                "event_type": outbox.event_type,
                "project_id": outbox.project_id,
                "attempts": attempts,
                "max_attempts": int(outbox.max_attempts),
                "error_code": code,
                "dead": dead,
                "retry_delay_seconds": delay_seconds,
            },
        )
        if not dead and next_attempt_at is not None:
            queue = Queue(settings.rq_queue_name, connection=Redis.from_url(settings.redis_url))
            queue.enqueue_in(timedelta(seconds=delay_seconds), process_outbox_delivery, kwargs={"outbox_id": outbox.id})
            logger.info(
                "Outbox delivery retry scheduled [outbox_id=%s kind=%s event_type=%s project_id=%s retry_delay_seconds=%s]",
                outbox.id,
                outbox.kind,
                outbox.event_type,
                outbox.project_id,
                delay_seconds,
                extra={
                    "outbox_id": outbox.id,
                    "kind": outbox.kind,
                    "event_type": outbox.event_type,
                    "project_id": outbox.project_id,
                    "retry_delay_seconds": delay_seconds,
                },
            )


def _deliver_webhook(*, outbox_id: str) -> None:
    settings = Settings()
    now = datetime.now(timezone.utc)
    outbox_repository = TransportOutboxRepositoryImpl(session_factory=DatabaseSessionFactory())
    project_repository = ProjectRepositoryImpl(session_factory=DatabaseSessionFactory())
    outbox = outbox_repository.get_by_id(outbox_id)
    if outbox is None:
        return
    project = project_repository.get_project(outbox.project_id)
    if project is None:
        return

    payload = dict(outbox.payload or {})
    transport_meta = payload.get("__transport_meta") if isinstance(payload.get("__transport_meta"), dict) else {}
    body_payload = payload.get("body") if isinstance(payload.get("body"), dict) else payload
    force_send = bool(transport_meta.get("force_send", False))

    if not force_send and (not project.protect_enabled or not project.webhook_enabled or not project.webhook_url):
        return

    target_url = outbox.destination or project.webhook_url
    if not target_url:
        return

    body_bytes = json.dumps(body_payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-RHEONIC-Event-Type": outbox.event_type,
    }
    override_secret = transport_meta.get("override_secret")
    signing_secret = str(override_secret) if isinstance(override_secret, str) else project.webhook_secret
    if signing_secret:
        digest = hmac.new(signing_secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        headers["X-RHEONIC-Signature"] = f"sha256={digest}"

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
    _ = now


def _deliver_email(*, outbox_id: str, settings: Settings) -> None:
    outbox_repository = TransportOutboxRepositoryImpl(session_factory=DatabaseSessionFactory())
    outbox = outbox_repository.get_by_id(outbox_id)
    if outbox is None:
        return
    destination = (outbox.destination or settings.feedback_report_email or "").strip()
    if not destination:
        raise ValueError("email destination is missing")
    if not outbox.template:
        raise ValueError("email template is required")

    rendered = render_template(outbox.template, dict(outbox.payload or {}))
    subject = (outbox.subject or rendered.get("subject") or "").strip()
    if not subject:
        raise ValueError("email subject is required")

    if not settings.email_provider_enabled:
        raise EmailProviderNotConfiguredError("email provider not configured")

    transport = NullEmailTransport()
    transport.send(
        to=destination,
        subject=subject,
        html=rendered.get("html") or "",
        text=rendered.get("text"),
    )


def _error_details(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, EmailProviderNotConfiguredError):
        return "email_provider_not_configured", "email provider not configured"
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return "webhook_http_error", f"HTTP {exc.response.status_code}"[: app_config.webhook_max_error_chars]
    message = str(exc).splitlines()[0][: app_config.webhook_max_error_chars]
    if isinstance(exc, httpx.TimeoutException):
        return "timeout", message
    return "delivery_failed", message


def _retry_delay_seconds(*, kind: str, attempt_number: int) -> int | None:
    if kind == "webhook":
        intervals = list(app_config.webhook_retry_intervals_seconds)
    else:
        intervals = list(app_config.email_retry_intervals_seconds)
    if not intervals:
        return None
    idx = min(max(attempt_number - 1, 0), len(intervals) - 1)
    return int(intervals[idx])
