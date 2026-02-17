# Shared input sanitization/validation helpers.
import re

from fastapi import HTTPException

NAME_MAX_LENGTH = 80
EMAIL_MAX_LENGTH = 320
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 _.-]+$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CONTROL_CHARS = ("\r", "\n", "\t")


def sanitize_email(value: str) -> str:
    # Normalize and validate email input.
    normalized = value.strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="email is required")
    if len(normalized) > EMAIL_MAX_LENGTH:
        raise HTTPException(status_code=400, detail="email is too long")
    if any(char in normalized for char in _CONTROL_CHARS):
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
    if len(normalized) > NAME_MAX_LENGTH:
        raise HTTPException(status_code=400, detail=f"{field_name} must be <= {NAME_MAX_LENGTH} chars")
    if any(char in normalized for char in _CONTROL_CHARS):
        raise HTTPException(status_code=400, detail=f"{field_name} contains invalid characters")
    if not _NAME_PATTERN.match(normalized):
        raise HTTPException(status_code=400, detail=f"{field_name} has invalid format")
    return normalized
