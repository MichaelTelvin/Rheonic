from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
from redis import Redis
from rq import Queue

from app.application.email_templates.registry import render_template
from app.application.interfaces.email_transport import EmailTransport
from app.application.services.transport_service import TransportService, build_transport_dedupe_key
from app.config import Settings, app_config
from app.domain.models.project import Project
from app.domain.models.transport_outbox import TransportOutbox
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.infrastructure.db.repositories.transport_outbox_repository_impl import TransportOutboxRepositoryImpl
from app.infrastructure.db.repositories.user_repository_impl import UserRepositoryImpl
from app.infrastructure.email.null_email_transport import EmailProviderNotConfiguredError, NullEmailTransport
from app.infrastructure.email.resend_email_transport import ResendEmailTransport, ResendEmailTransportError
from app.logger import (
    bind_trace_context,
    build_log_extra,
    configure_logging,
    generate_span_id,
    generate_trace_id,
    get_logger,
    get_trace_id,
    reset_trace_context,
)
from app.security.webhook_urls import ensure_webhook_url_is_safe

logger = get_logger(__name__)

_SYSTEM_EMAIL_EVENTS = {"feedback.submitted"}
_ALERT_EMAIL_EVENTS = {
    "protection.warn",
    "protection.clamp_started",
    "protection.block",
    "incident.resolved",
    "webhook.delivery_failed",
}


def enqueue_outbox_delivery(outbox_id: str, *, trace_id: str | None = None, span_id: str | None = None) -> None:
    settings = Settings()
    queue = Queue(settings.rq_queue_name, connection=Redis.from_url(settings.redis_url))
    queue.enqueue(
        process_outbox_delivery,
        kwargs={
            "outbox_id": outbox_id,
            "trace_id": trace_id or generate_trace_id(),
            "span_id": span_id or generate_span_id(),
        },
    )


def process_outbox_delivery(outbox_id: str, *, trace_id: str | None = None, span_id: str | None = None) -> None:
    settings = Settings()
    configure_logging(service_name="worker", level=settings.log_level)
    context_tokens = bind_trace_context(trace_id=trace_id, span_id=span_id)
    now = datetime.now(timezone.utc)
    repository = TransportOutboxRepositoryImpl(session_factory=DatabaseSessionFactory())
    outbox = repository.claim_for_send(outbox_id=outbox_id, now=now)
    if outbox is None:
        logger.info(
            "Outbox delivery skipped; row unavailable",
            extra=build_log_extra(event="outbox_skipped", metadata={"outbox_id": outbox_id}),
        )
        reset_trace_context(context_tokens)
        return

    delivery_metadata: dict[str, object] = {}
    correlation_metadata = _outbox_correlation_metadata(outbox)
    try:
        if outbox.kind == "webhook":
            delivery_metadata = _deliver_webhook(outbox_id=outbox.id)
        elif outbox.kind == "email":
            delivery_metadata = _deliver_email(outbox_id=outbox.id, settings=settings)
        else:
            raise RuntimeError(f"unsupported transport kind: {outbox.kind}")
        repository.mark_delivered(outbox_id=outbox.id, now=datetime.now(timezone.utc))
        success_metadata: dict[str, object] = {
            "outbox_id": outbox.id,
            "kind": outbox.kind,
            "event_type": outbox.event_type,
            "project_id": outbox.project_id,
        }
        success_metadata.update(correlation_metadata)
        success_metadata.update(delivery_metadata)
        if bool(success_metadata.pop("skipped", False)):
            logger.info(
                "Outbox delivery skipped",
                extra=build_log_extra(
                    event="outbox_skipped",
                    metadata=success_metadata,
                ),
            )
            return
        logger.info(
            "Outbox delivery succeeded",
            extra=build_log_extra(
                event="outbox_delivered",
                metadata=success_metadata,
            ),
        )
    except Exception as exc:
        attempts = max(int(outbox.attempts), 1)
        delay_seconds = _retry_delay_seconds(kind=outbox.kind, attempt_number=attempts)
        dead = attempts >= int(outbox.max_attempts) or delay_seconds is None
        next_attempt_at = (
            None if dead or delay_seconds is None else datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        )
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
            "Outbox delivery failed",
            extra=build_log_extra(
                event="webhook_failed" if outbox.kind == "webhook" else "email_failed",
                metadata={
                    "outbox_id": outbox.id,
                    "kind": outbox.kind,
                    "event_type": outbox.event_type,
                    "project_id": outbox.project_id,
                    "attempts": attempts,
                    "max_attempts": int(outbox.max_attempts),
                    **correlation_metadata,
                    "error_code": code,
                    "error_message": message,
                    "dead": dead,
                    "retry_delay_seconds": delay_seconds,
                },
            ),
        )
        if outbox.kind == "webhook" and dead:
            try:
                failed_outbox = repository.get_by_id(outbox.id)
                if failed_outbox is not None:
                    _enqueue_webhook_failure_email(outbox=failed_outbox, settings=settings)
            except Exception:
                logger.exception(
                    "Failed to enqueue webhook terminal failure email",
                    extra=build_log_extra(
                        event="error",
                        metadata={
                            "outbox_id": outbox.id,
                            "project_id": outbox.project_id,
                            "event_type": outbox.event_type,
                        },
                    ),
                )
        if not dead and next_attempt_at is not None:
            retry_delay_seconds = delay_seconds if isinstance(delay_seconds, int) else 0
            queue = Queue(settings.rq_queue_name, connection=Redis.from_url(settings.redis_url))
            queue.enqueue_in(
                timedelta(seconds=retry_delay_seconds),
                process_outbox_delivery,
                kwargs={
                    "outbox_id": outbox.id,
                    "trace_id": trace_id or generate_trace_id(),
                    "span_id": generate_span_id(),
                },
            )
            logger.info(
                "Outbox delivery retry scheduled",
                extra=build_log_extra(
                    event="outbox_retry_scheduled",
                    metadata={
                        "outbox_id": outbox.id,
                        "kind": outbox.kind,
                        "event_type": outbox.event_type,
                        "project_id": outbox.project_id,
                        "retry_delay_seconds": retry_delay_seconds,
                    },
                ),
            )
    finally:
        reset_trace_context(context_tokens)


def _outbox_correlation_metadata(outbox: TransportOutbox) -> dict[str, object]:
    payload = dict(outbox.payload or {})
    transport_meta_value = payload.get("__transport_meta")
    transport_meta = transport_meta_value if isinstance(transport_meta_value, dict) else {}
    body_payload_value = payload.get("body")
    body_payload = body_payload_value if isinstance(body_payload_value, dict) else payload
    metadata: dict[str, object] = {}
    origin_trace_id = transport_meta.get("origin_trace_id")
    if isinstance(origin_trace_id, str) and origin_trace_id.strip():
        metadata["origin_trace_id"] = origin_trace_id.strip()
    for field in ("incident_id", "provider", "model", "environment"):
        value = body_payload.get(field)
        if isinstance(value, str) and value.strip():
            metadata[field] = value.strip()
    return metadata


def _deliver_webhook(*, outbox_id: str) -> dict[str, object]:
    settings = Settings()
    now = datetime.now(timezone.utc)
    outbox_repository = TransportOutboxRepositoryImpl(session_factory=DatabaseSessionFactory())
    project_repository = ProjectRepositoryImpl(session_factory=DatabaseSessionFactory())
    outbox = outbox_repository.get_by_id(outbox_id)
    if outbox is None:
        return {"skipped": True, "skip_reason": "outbox_missing"}
    project = project_repository.get_project(outbox.project_id)
    if project is None:
        return {"skipped": True, "skip_reason": "project_missing"}

    payload = dict(outbox.payload or {})
    transport_meta_value = payload.get("__transport_meta")
    transport_meta = transport_meta_value if isinstance(transport_meta_value, dict) else {}
    body_payload_value = payload.get("body")
    body_payload = body_payload_value if isinstance(body_payload_value, dict) else payload
    force_send = bool(transport_meta.get("force_send", False))

    if not force_send and (not project.webhook_enabled or not project.webhook_url):
        return {
            "skipped": True,
            "skip_reason": "webhook_disabled_or_missing_url",
            "webhook_enabled": bool(project.webhook_enabled),
            "destination": (project.webhook_url or "").strip() or None,
        }

    target_url = outbox.destination or project.webhook_url
    if not target_url:
        return {"skipped": True, "skip_reason": "webhook_destination_missing"}

    rendered_body = body_payload

    body_bytes = json.dumps(rendered_body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-RHEONIC-Event-Type": outbox.event_type,
        "X-Trace-ID": get_trace_id() or generate_trace_id(),
        "X-Span-ID": generate_span_id(),
    }
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
    return {
        "destination": target_url,
        "status_code": getattr(response, "status_code", None),
    }


def _deliver_email(*, outbox_id: str, settings: Settings) -> dict[str, object]:
    outbox_repository = TransportOutboxRepositoryImpl(session_factory=DatabaseSessionFactory())
    project_repository = ProjectRepositoryImpl(session_factory=DatabaseSessionFactory())
    user_repository = UserRepositoryImpl(session_factory=DatabaseSessionFactory())
    outbox = outbox_repository.get_by_id(outbox_id)
    if outbox is None:
        return {"skipped": True, "skip_reason": "outbox_missing"}
    project = project_repository.get_project(outbox.project_id)

    # Feedback is an internal workflow. Project alerts resolve to the owning user
    # and respect the project's protect/email switches at delivery time.
    destination = _resolve_email_destination(
        outbox=outbox,
        project=project,
        settings=settings,
        user_repository=user_repository,
    )
    if destination is None:
        return {
            "skipped": True,
            "skip_reason": "email_disabled_or_missing_project",
            "destination": None,
        }
    if not destination:
        raise ValueError("email destination is missing")
    if not outbox.template:
        raise ValueError("email template is required")

    rendered = render_template(outbox.template, dict(outbox.payload or {}))
    subject = (outbox.subject or rendered.get("subject") or "").strip()
    if not subject:
        raise ValueError("email subject is required")

    if not settings.resolved_email_provider_enabled:
        raise EmailProviderNotConfiguredError("email provider not configured")

    sender = _resolve_email_sender(settings=settings, event_type=outbox.event_type)
    reply_to = (settings.email_reply_to or "").strip() or None
    transport = _build_email_transport(settings=settings)
    attachments = _extract_email_attachments(outbox.payload or {})
    transport.send(
        to=destination,
        subject=subject,
        html=rendered.get("html") or "",
        text=rendered.get("text"),
        from_email=sender,
        reply_to=reply_to,
        attachments=attachments,
    )
    return {"destination": destination}


def _error_details(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, EmailProviderNotConfiguredError):
        return "email_provider_not_configured", "email provider not configured"
    if isinstance(exc, ResendEmailTransportError):
        return exc.code, str(exc)[: app_config.webhook_max_error_chars]
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


def _resolve_email_destination(
    *,
    outbox: TransportOutbox,
    project: Project | None,
    settings: Settings,
    user_repository: UserRepositoryImpl,
) -> str | None:
    explicit_destination = (outbox.destination or "").strip()
    if explicit_destination:
        return explicit_destination
    if outbox.event_type == "feedback.submitted":
        return (settings.feedback_report_email or "").strip()
    if project is None:
        return None
    if not project.protect_enabled or not project.email_enabled:
        return None
    if not project.user_id:
        raise ValueError("project owner is missing for alert email delivery")
    user = user_repository.get_by_id(project.user_id)
    if user is None or not (user.email or "").strip():
        raise ValueError("project owner email is missing for alert email delivery")
    return user.email.strip()


def _resolve_email_sender(*, settings: Settings, event_type: str) -> str:
    if event_type in _SYSTEM_EMAIL_EVENTS:
        sender = (settings.email_from_system or "").strip()
    elif event_type in _ALERT_EMAIL_EVENTS:
        sender = (settings.email_from_alerts or "").strip()
    else:
        raise ValueError(f"unsupported email event type: {event_type}")
    if not sender:
        raise ValueError(f"sender is missing for email event type: {event_type}")
    return sender


def _build_email_transport(*, settings: Settings) -> EmailTransport:
    provider = settings.resolved_email_provider
    if provider == "resend":
        return ResendEmailTransport(api_key=settings.resend_api_key)
    if provider:
        raise ValueError(f"unsupported email provider: {provider}")
    return NullEmailTransport()


def _extract_email_attachments(payload: dict[str, object]) -> list[dict[str, str]] | None:
    screenshot_name = str(payload.get("screenshot_name") or "").strip()
    screenshot_content_type = str(payload.get("screenshot_content_type") or "").strip()
    screenshot_base64 = str(payload.get("screenshot_base64") or "").strip()
    if not screenshot_name or not screenshot_content_type or not screenshot_base64:
        return None
    return [
        {
            "filename": screenshot_name,
            "content": screenshot_base64,
            "content_type": screenshot_content_type,
        }
    ]


def _enqueue_webhook_failure_email(*, outbox: TransportOutbox, settings: Settings) -> None:
    if outbox.event_type == "webhook.test":
        return
    project_repository = ProjectRepositoryImpl(session_factory=DatabaseSessionFactory())
    project = project_repository.get_project(outbox.project_id)
    if project is None or not project.protect_enabled or not project.webhook_enabled or not project.email_enabled:
        return

    payload: dict[str, object] = {
        "project_id": outbox.project_id,
        "event_type": outbox.event_type,
        "destination": outbox.destination or project.webhook_url,
        "status": outbox.status,
        "attempts": int(outbox.attempts),
        "max_attempts": int(outbox.max_attempts),
        "last_error_code": outbox.last_error_code,
        "last_error_message": outbox.last_error_message,
        "updated_at": outbox.updated_at.isoformat() if outbox.updated_at is not None else None,
    }
    transport_service = TransportService(
        outbox_repository=TransportOutboxRepositoryImpl(session_factory=DatabaseSessionFactory()),
        enqueue_job=enqueue_outbox_delivery,
    )
    dedupe_key = build_transport_dedupe_key(
        project_id=outbox.project_id,
        kind="email",
        event_type="webhook.delivery_failed",
        payload=payload,
        seed=outbox.id,
    )
    transport_service.enqueue(
        project_id=outbox.project_id,
        kind="email",
        event_type="webhook.delivery_failed",
        payload=payload,
        dedupe_key=dedupe_key,
        template="webhook_delivery_failed",
    )
