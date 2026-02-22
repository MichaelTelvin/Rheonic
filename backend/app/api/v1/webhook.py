# Project webhook configuration endpoints.
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AnyHttpUrl, BaseModel, field_validator

from app.application.services.project_service import ProjectService
from app.dependencies import get_current_user, get_project_service, get_webhook_dispatcher
from app.domain.models.user import User
from app.infrastructure.alerts.rq_webhook_dispatcher import RQWebhookDispatcher
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class ProjectWebhookOut(BaseModel):
    # Project webhook settings response payload.
    enabled: bool
    url: str | None
    has_secret: bool
    last_status: str | None
    last_at: datetime | None
    last_error: str | None


class ProjectWebhookIn(BaseModel):
    # Project webhook settings update payload.
    enabled: bool
    url: AnyHttpUrl | None = None
    secret: str | None = None

    @field_validator("secret")
    @classmethod
    def normalize_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


@router.get("/projects/{project_id}/webhook", response_model=ProjectWebhookOut)
def get_project_webhook(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> ProjectWebhookOut:
    # Return webhook configuration for an owned project.
    try:
        project = project_service.get_project_webhook_settings(project_id=project_id, user_id=current_user.id)
        return ProjectWebhookOut(
            enabled=project.webhook_enabled,
            url=project.webhook_url,
            has_secret=bool(project.webhook_secret),
            last_status=project.webhook_last_status,
            last_at=project.webhook_last_at,
            last_error=project.webhook_last_error,
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
    current_user: User = Depends(get_current_user),
) -> ProjectWebhookOut:
    # Update webhook configuration for an owned project.
    try:
        normalized_url = str(payload.url) if payload.url is not None else None
        if payload.enabled and not normalized_url:
            raise HTTPException(status_code=422, detail="url is required when webhook is enabled")
        updated = project_service.update_project_webhook_settings(
            project_id=project_id,
            user_id=current_user.id,
            webhook_enabled=payload.enabled,
            webhook_url=normalized_url,
            webhook_secret=payload.secret,
        )
        return ProjectWebhookOut(
            enabled=updated.webhook_enabled,
            url=updated.webhook_url,
            has_secret=bool(updated.webhook_secret),
            last_status=updated.webhook_last_status,
            last_at=updated.webhook_last_at,
            last_error=updated.webhook_last_error,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Update project webhook failed", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to update project webhook settings")


@router.post("/projects/{project_id}/webhook/test", status_code=202)
def test_project_webhook(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    dispatcher: RQWebhookDispatcher = Depends(get_webhook_dispatcher),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    # Enqueue a webhook test payload for an owned project.
    try:
        project_service.get_project_webhook_settings(project_id=project_id, user_id=current_user.id)
        dispatcher.enqueue(
            project_id=project_id,
            event_type="webhook.test",
            payload={
                "event": "webhook.test",
                "project_id": project_id,
                "sent_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return {"status": "queued"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Test project webhook failed", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to enqueue webhook test")
