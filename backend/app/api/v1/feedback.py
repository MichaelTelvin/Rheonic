# Beta feedback API endpoint.
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_current_user, get_feedback_mailer
from app.domain.models.user import User
from app.infrastructure.notifications.feedback_mailer import FeedbackMailer
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class FeedbackIn(BaseModel):
    # Frontend feedback payload.
    message: str
    email: str | None = None
    project_id: str | None = None
    page: str | None = None
    mode: str | None = None
    timestamp: str | None = None
    app_version: str | None = None


@router.post("/feedback")
def send_feedback(
    payload: FeedbackIn,
    current_user: User = Depends(get_current_user),
    mailer: FeedbackMailer = Depends(get_feedback_mailer),
) -> dict[str, str]:
    # Accept beta feedback and deliver it to configured report inbox.
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    event_time = payload.timestamp or datetime.now(timezone.utc).isoformat()
    body = "\n".join(
        [
            "Rheonic beta feedback",
            "",
            f"message: {message}",
            f"email: {(payload.email or '').strip() or current_user.email}",
            f"user_id: {current_user.id}",
            f"user_email: {current_user.email}",
            f"project_id: {(payload.project_id or '').strip() or '-'}",
            f"page: {(payload.page or '').strip() or '-'}",
            f"mode: {(payload.mode or '').strip() or '-'}",
            f"timestamp: {event_time}",
            f"app_version: {(payload.app_version or '').strip() or '-'}",
        ]
    )

    try:
        mailer.send(subject="Rheonic beta feedback", body=body)
        return {"status": "sent"}
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Feedback send failed")
        raise HTTPException(status_code=500, detail="failed to send feedback")
