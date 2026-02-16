# Event ingest endpoints.
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, ConfigDict, Field

from app.application.services.ingest_event_service import IngestEventService
from app.dependencies import get_ingest_event_service
from app.domain.models.event import Event
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class EventRequestIn(BaseModel):
    # Nested request payload tokens.
    model_config = ConfigDict(extra="ignore")

    input_tokens: int | None = None


class EventResponseIn(BaseModel):
    # Nested response payload tokens.
    model_config = ConfigDict(extra="ignore")

    output_tokens: int | None = None
    total_tokens: int | None = None


class EventIn(BaseModel):
    # Validated request body for event ingest.
    model_config = ConfigDict(extra="ignore")

    ts: datetime
    provider: str
    model: str | None = None
    environment: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int | None = Field(default=None)
    latency_ms: int | None = None
    status: str | None = None
    error_type: str | None = None
    http_status: int | None = None
    request: EventRequestIn | None = None
    response: EventResponseIn | None = None


def _resolve_tokens(payload: EventIn) -> tuple[int, int, int]:
    # Resolve normalized input/output/total tokens using ingest precedence.
    request = payload.request
    response = payload.response

    # compute normalized input/output fallback values
    input_tokens = (request.input_tokens if request is not None else payload.input_tokens) or 0
    output_tokens = (response.output_tokens if response is not None else payload.output_tokens) or 0

    # apply precedence for total tokens
    if response is not None and response.total_tokens is not None:
        return input_tokens, output_tokens, response.total_tokens

    # fallback to request + response tokens when nested values exist
    if request is not None and response is not None:
        return input_tokens, output_tokens, (request.input_tokens or 0) + (response.output_tokens or 0)

    # final fallback
    return input_tokens, output_tokens, 0


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def ingest_event(
    payload: EventIn,
    service: IngestEventService = Depends(get_ingest_event_service),
    ingest_key: str | None = Header(default=None, alias="X-Project-Ingest-Key"),
) -> dict[str, str]:
    # Receive an SDK event and delegate processing to application services.
    try:
        if not ingest_key:
            raise HTTPException(status_code=401, detail="missing ingest key")

        # normalize token values from payload
        input_tokens, output_tokens, total_tokens = _resolve_tokens(payload)

        # build the domain event object
        event = Event(
            id=str(uuid4()),
            ts=payload.ts,
            project_id=ingest_key,
            provider=payload.provider,
            model=payload.model,
            environment=payload.environment,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=payload.latency_ms,
            status=payload.status,
            error_type=payload.error_type,
            http_status=payload.http_status,
            created_at=datetime.now(timezone.utc),
        )

        # execute ingest use-case
        service.ingest(event)
        logger.info("Event accepted", extra={"project_id": ingest_key, "provider": payload.provider})
        return {"status": "accepted"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Event ingest failed", extra={"project_id": ingest_key})
        raise HTTPException(status_code=500, detail="Failed to ingest event")
