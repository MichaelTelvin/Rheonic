# Beta feedback API endpoint.
import base64
import binascii
import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator, model_validator

from app.application.services.transport_service import TransportService, build_transport_dedupe_key
from app.dependencies import get_current_user, get_transport_service
from app.domain.models.user import User
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

_MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024
_MAX_PAGE_LENGTH = 200
_ALLOWED_SCREENSHOT_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
_SAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _normalize_filename(value: str) -> str:
    raw = value.strip().replace("\\", "/").split("/")[-1]
    cleaned = _SAFE_FILENAME_CHARS.sub("-", raw).strip(".- ")
    return cleaned[:120]


class FeedbackIn(BaseModel):
    # Frontend feedback payload.
    report_type: Literal["feedback", "bug"] | None = None
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

    @field_validator("page")
    @classmethod
    def validate_page(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if len(normalized) > _MAX_PAGE_LENGTH:
            raise ValueError("page is too long")
        return normalized

    @field_validator("screenshot_content_type")
    @classmethod
    def validate_screenshot_content_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in _ALLOWED_SCREENSHOT_CONTENT_TYPES:
            raise ValueError("unsupported screenshot content type")
        return normalized

    @field_validator("screenshot_name")
    @classmethod
    def validate_screenshot_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_filename(value)
        if not normalized:
            raise ValueError("invalid screenshot filename")
        return normalized

    @field_validator("screenshot_base64")
    @classmethod
    def validate_screenshot_base64(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        max_encoded_length = ((_MAX_SCREENSHOT_BYTES + 2) // 3) * 4 + 8
        if len(normalized) > max_encoded_length:
            raise ValueError("screenshot is too large")
        try:
            decoded = base64.b64decode(normalized, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("invalid screenshot payload") from exc
        if len(decoded) > _MAX_SCREENSHOT_BYTES:
            raise ValueError("screenshot is too large")
        return normalized

    @model_validator(mode="after")
    def validate_screenshot_fields(self) -> "FeedbackIn":
        fields = [self.screenshot_name, self.screenshot_content_type, self.screenshot_base64]
        if any(fields) and not all(fields):
            raise ValueError("screenshot attachment is incomplete")
        return self


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
