"""Event ingest endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.application.services.ingest_event_service import IngestEventService
from app.dependencies import get_ingest_event_service

router = APIRouter()


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(
    payload: dict[str, Any],
    service: IngestEventService = Depends(get_ingest_event_service),
) -> dict[str, str]:
    """Receive an SDK event and delegate processing to application services."""
    _ = service
    # TODO: Define request/response schemas and call service.
    return {"status": "accepted"}
