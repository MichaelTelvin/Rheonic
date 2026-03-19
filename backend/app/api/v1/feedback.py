# Beta feedback API endpoint.
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.application.services.transport_service import TransportService, build_transport_dedupe_key
from app.dependencies import get_current_user, get_transport_service
from app.domain.models.user import User
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class FeedbackIn(BaseModel):
    # Frontend feedback payload.
    report_type: str | None = None
    message: str
    email: str | None = None
    screenshot_name: str | None = None
    screenshot_content_type: str | None = None
    screenshot_base64: str | None = None
    project_id: str | None = None
    page: str | None = None
    mode: str | None = None
    timestamp: str | None = None
    app_version: str | None = None


@router.post("/feedback", status_code=202)
def send_feedback(
    payload: FeedbackIn,
    current_user: User = Depends(get_current_user),
    transport_service: TransportService = Depends(get_transport_service),
) -> dict[str, str]:
    # Accept beta feedback and enqueue async email delivery.
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    event_time = payload.timestamp or datetime.now(timezone.utc).isoformat()
    screenshot_name = (payload.screenshot_name or "").strip()
    screenshot_content_type = (payload.screenshot_content_type or "").strip()
    screenshot_base64 = (payload.screenshot_base64 or "").strip()
    payload_body: dict[str, object] = {
        "report_type": (payload.report_type or "").strip() or "feedback",
        "message": message,
        "email": (payload.email or "").strip() or current_user.email,
        "user_id": current_user.id,
        "user_email": current_user.email,
        "project_id": (payload.project_id or "").strip() or "-",
        "page": (payload.page or "").strip() or "-",
        "mode": (payload.mode or "").strip() or "-",
        "timestamp": event_time,
        "app_version": (payload.app_version or "").strip() or "-",
    }
    if screenshot_name and screenshot_content_type and screenshot_base64:
        payload_body["screenshot_name"] = screenshot_name
        payload_body["screenshot_content_type"] = screenshot_content_type
        payload_body["screenshot_base64"] = screenshot_base64

    try:
        dedupe_key = build_transport_dedupe_key(
            project_id=(payload.project_id or "").strip() or "global",
            kind="email",
            event_type="feedback.submitted",
            payload=payload_body,
            destination=None,
            seed=current_user.id,
        )
        transport_service.enqueue(
            project_id=(payload.project_id or "").strip() or "global",
            kind="email",
            event_type="feedback.submitted",
            payload=payload_body,
            dedupe_key=dedupe_key,
            destination=None,
            template="feedback_submitted",
        )
        return {"status": "queued"}
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Feedback send failed")
        raise HTTPException(status_code=500, detail="failed to send feedback")
