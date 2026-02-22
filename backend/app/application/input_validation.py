# Shared input sanitization/validation helpers.
import re

from fastapi import HTTPException

from app.config import app_config

_NAME_PATTERN = re.compile(app_config.name_validation_pattern)
_EMAIL_PATTERN = re.compile(app_config.email_validation_pattern)


def sanitize_email(value: str) -> str:
    # Normalize and validate email input.
    normalized = value.strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="email is required")
    if len(normalized) > app_config.email_max_length:
        raise HTTPException(status_code=400, detail="email is too long")
    if any(char in normalized for char in app_config.control_chars):
        raise HTTPException(status_code=400, detail="email contains invalid characters")
    if not _EMAIL_PATTERN.match(normalized):
        raise HTTPException(status_code=400, detail="invalid email format")
    return normalized


def sanitize_project_name(value: str) -> str:
    # Normalize and validate project name input.
    return _sanitize_name(value=value, field_name="project name")


def sanitize_key_label(value: str) -> str:
    # Normalize and validate key label input.
    return _sanitize_name(value=value, field_name="key label")


def _sanitize_name(value: str, field_name: str) -> str:
    # Normalize and validate project/key names.
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    if len(normalized) > app_config.name_max_length:
        raise HTTPException(status_code=400, detail=f"{field_name} must be <= {app_config.name_max_length} chars")
    if any(char in normalized for char in app_config.control_chars):
        raise HTTPException(status_code=400, detail=f"{field_name} contains invalid characters")
    if not _NAME_PATTERN.match(normalized):
        raise HTTPException(status_code=400, detail=f"{field_name} has invalid format")
    return normalized
