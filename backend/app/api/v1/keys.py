# Ingest key management endpoints.
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.application.services.ingest_key_service import IngestKeyService
from app.config import Settings
from app.dependencies import get_ingest_key_service, get_settings
from app.domain.models.ingest_key import IngestKey
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class KeySummaryOut(BaseModel):
    # Public key summary response without plaintext secret.
    id: str
    name: str
    last4: str | None
    status: str
    created_at: datetime
    revoked_at: datetime | None


class CreateKeyIn(BaseModel):
    # API request model for key creation.
    name: str


class CreateKeyOut(BaseModel):
    # API response model for one-time plaintext key creation output.
    key: str
    key_id: str
    name: str
    last4: str | None
    created_at: datetime


def _enforce_dev_mode(settings: Settings) -> None:
    # Block management endpoints outside dev mode.
    if settings.app_env != "dev":
        raise HTTPException(status_code=403, detail="not enabled")


def _summary(key: IngestKey) -> KeySummaryOut:
    # Build API summary object from domain key.
    return KeySummaryOut(
        id=key.id,
        name=key.name,
        last4=key.last4,
        status=key.status,
        created_at=key.created_at,
        revoked_at=key.revoked_at,
    )


@router.get("/projects/{project_id}/keys", response_model=list[KeySummaryOut])
def list_project_keys(
    project_id: str,
    service: IngestKeyService = Depends(get_ingest_key_service),
) -> list[KeySummaryOut]:
    # List project ingest keys without plaintext values.
    try:
        return [_summary(key) for key in service.list_keys(project_id=project_id)]
    except HTTPException:
        raise
    except Exception:
        logger.exception("List project keys endpoint failed", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to list keys")


@router.post("/projects/{project_id}/keys", response_model=CreateKeyOut)
def create_project_key(
    project_id: str,
    payload: CreateKeyIn,
    service: IngestKeyService = Depends(get_ingest_key_service),
    settings: Settings = Depends(get_settings),
) -> CreateKeyOut:
    # Create new key and return plaintext once.
    try:
        _enforce_dev_mode(settings)
        key, plaintext = service.create_key(project_id=project_id, name=payload.name)
        return CreateKeyOut(
            key=plaintext,
            key_id=key.id,
            name=key.name,
            last4=key.last4,
            created_at=key.created_at,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Create key endpoint failed", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to create key")


@router.post("/keys/{key_id}/revoke", response_model=KeySummaryOut)
def revoke_key(
    key_id: str,
    service: IngestKeyService = Depends(get_ingest_key_service),
    settings: Settings = Depends(get_settings),
) -> KeySummaryOut:
    # Revoke key and return key summary.
    try:
        _enforce_dev_mode(settings)
        key = service.revoke_key(key_id=key_id)
        return _summary(key)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Revoke key endpoint failed", extra={"key_id": key_id})
        raise HTTPException(status_code=500, detail="Failed to revoke key")


@router.post("/keys/{key_id}/rotate", response_model=CreateKeyOut)
def rotate_key(
    key_id: str,
    service: IngestKeyService = Depends(get_ingest_key_service),
    settings: Settings = Depends(get_settings),
) -> CreateKeyOut:
    # Rotate key and return new plaintext once.
    try:
        _enforce_dev_mode(settings)
        key, plaintext = service.rotate_key(key_id=key_id)
        return CreateKeyOut(
            key=plaintext,
            key_id=key.id,
            name=key.name,
            last4=key.last4,
            created_at=key.created_at,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Rotate key endpoint failed", extra={"key_id": key_id})
        raise HTTPException(status_code=500, detail="Failed to rotate key")
