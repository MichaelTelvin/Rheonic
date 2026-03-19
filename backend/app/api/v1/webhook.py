# Project webhook configuration endpoints.
from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException
import httpx
from pydantic import AnyHttpUrl, BaseModel

from app.application.interfaces.transport_outbox_repository import TransportOutboxRepository
from app.application.services.project_service import ProjectService
from app.config import Settings
from app.dependencies import (
    get_current_user,
    get_project_service,
    get_settings,
    get_transport_outbox_repository,
)
from app.domain.models.user import User
from app.logger import get_logger
from app.observability import generate_span_id, generate_trace_id, get_trace_id
from app.security.webhook_urls import ensure_webhook_url_is_safe, normalize_webhook_url

logger = get_logger(__name__)
router = APIRouter()
WEBHOOK_STATUS_EXCLUDED_EVENT_TYPES = ("webhook.test",)


class ProjectWebhookOut(BaseModel):
    # Project webhook settings response payload.
    enabled: bool
    email_enabled: bool
    url: str | None
    last_status: str | None
    last_at: datetime | None
    last_error: str | None


class ProjectWebhookIn(BaseModel):
    # Project webhook settings update payload.
    enabled: bool
    email_enabled: bool = False
    url: AnyHttpUrl | None = None


class ProjectWebhookTestIn(BaseModel):
    # Optional draft values for webhook test sends.
    url: AnyHttpUrl | None = None


class ProjectWebhookTestOut(BaseModel):
    # Synchronous webhook test result for customer-visible feedback.
    status: str
    status_code: int | None = None
    error: str | None = None


@router.get("/projects/{project_id}/webhook", response_model=ProjectWebhookOut)
def get_project_webhook(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    transport_outbox_repository: TransportOutboxRepository = Depends(get_transport_outbox_repository),
    current_user: User = Depends(get_current_user),
) -> ProjectWebhookOut:
    # Return webhook configuration for an owned project.
    try:
        project = project_service.get_project_webhook_settings(project_id=project_id, user_id=current_user.id)
        return ProjectWebhookOut(
            enabled=project.webhook_enabled,
            email_enabled=project.email_enabled,
            url=project.webhook_url,
            last_status=_last_status_from_outbox(project_id=project_id, outbox_repository=transport_outbox_repository),
            last_at=_last_at_from_outbox(project_id=project_id, outbox_repository=transport_outbox_repository),
            last_error=_last_error_from_outbox(project_id=project_id, outbox_repository=transport_outbox_repository),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Get project webhook failed", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to fetch project webhook settings")


@router.put("/projects/{project_id}/webhook", response_model=ProjectWebhookOut)
def update_project_webhook(
    project_id: str,
    payload: ProjectWebhookIn,
    project_service: ProjectService = Depends(get_project_service),
    transport_outbox_repository: TransportOutboxRepository = Depends(get_transport_outbox_repository),
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(get_current_user),
) -> ProjectWebhookOut:
    # Update webhook configuration for an owned project.
    try:
        project_service.get_project_webhook_settings(project_id=project_id, user_id=current_user.id)
        normalized_url = normalize_webhook_url(str(payload.url) if payload.url is not None else None)
        if normalized_url is not None:
            ensure_webhook_url_is_safe(normalized_url, settings=settings)
        if payload.enabled and not normalized_url:
            raise HTTPException(status_code=422, detail="url is required when webhook is enabled")
        updated = project_service.update_project_webhook_settings(
            project_id=project_id,
            user_id=current_user.id,
            webhook_enabled=payload.enabled,
            email_enabled=payload.email_enabled,
            webhook_url=normalized_url,
        )
        return ProjectWebhookOut(
            enabled=updated.webhook_enabled,
            email_enabled=updated.email_enabled,
            url=updated.webhook_url,
            last_status=_last_status_from_outbox(project_id=project_id, outbox_repository=transport_outbox_repository),
            last_at=_last_at_from_outbox(project_id=project_id, outbox_repository=transport_outbox_repository),
            last_error=_last_error_from_outbox(project_id=project_id, outbox_repository=transport_outbox_repository),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Update project webhook failed", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to update project webhook settings")


@router.post("/projects/{project_id}/webhook/test", response_model=ProjectWebhookTestOut)
def test_project_webhook(
    project_id: str,
    payload: ProjectWebhookTestIn | None = None,
    project_service: ProjectService = Depends(get_project_service),
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(get_current_user),
) -> ProjectWebhookTestOut:
    # Send a webhook test payload immediately and return the real delivery result.
    try:
        project = project_service.get_project_webhook_settings(project_id=project_id, user_id=current_user.id)
        override_url = normalize_webhook_url(str(payload.url) if payload and payload.url is not None else None)
        target_url = override_url or project.webhook_url
        if not target_url:
            raise HTTPException(status_code=422, detail="url is required for webhook test")
        ensure_webhook_url_is_safe(target_url, settings=settings)
        response = _send_webhook_test_request(project_id=project_id, target_url=target_url, settings=settings)
        logger.info(
            "Webhook test delivered",
            extra={"project_id": project_id, "destination": target_url, "status_code": response.status_code},
        )
        return ProjectWebhookTestOut(status="success", status_code=response.status_code)
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        error = f"HTTP {status_code}" if status_code is not None else "HTTP error"
        return ProjectWebhookTestOut(status="failed", status_code=status_code, error=error)
    except httpx.TimeoutException:
        return ProjectWebhookTestOut(status="failed", error="Timed out")
    except httpx.HTTPError as exc:
        return ProjectWebhookTestOut(status="failed", error=str(exc) or "Network error")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Test project webhook failed", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to send webhook test")


def _send_webhook_test_request(*, project_id: str, target_url: str, settings: Settings) -> httpx.Response:
    payload = {
        "event": "webhook.test",
        "project_id": project_id,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    body_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-RHEONIC-Event-Type": "webhook.test",
        "X-Trace-ID": get_trace_id() or generate_trace_id(),
        "X-Span-ID": generate_span_id(),
    }
    timeout = httpx.Timeout(
        connect=settings.webhook_timeout_connect_seconds,
        read=settings.webhook_timeout_read_seconds,
        write=settings.webhook_timeout_write_seconds,
        pool=settings.webhook_timeout_pool_seconds,
    )
    with httpx.Client(timeout=timeout) as client:
        response = client.post(target_url, content=body_bytes, headers=headers)
        response.raise_for_status()
        return response


def _latest_terminal(project_id: str, outbox_repository: TransportOutboxRepository):
    return outbox_repository.get_latest_terminal_by_project_kind(
        project_id=project_id,
        kind="webhook",
        exclude_event_types=WEBHOOK_STATUS_EXCLUDED_EVENT_TYPES,
    )


def _last_status_from_outbox(*, project_id: str, outbox_repository: TransportOutboxRepository) -> str | None:
    latest = _latest_terminal(project_id=project_id, outbox_repository=outbox_repository)
    if latest is None:
        return None
    if latest.status == "delivered":
        return "success"
    if latest.status in {"failed", "dead"}:
        return "failed"
    return None


def _last_at_from_outbox(*, project_id: str, outbox_repository: TransportOutboxRepository) -> datetime | None:
    latest = _latest_terminal(project_id=project_id, outbox_repository=outbox_repository)
    if latest is None:
        return None
    return latest.delivered_at or latest.updated_at


def _last_error_from_outbox(*, project_id: str, outbox_repository: TransportOutboxRepository) -> str | None:
    latest = _latest_terminal(project_id=project_id, outbox_repository=outbox_repository)
    if latest is None:
        return None
    return latest.last_error_message
