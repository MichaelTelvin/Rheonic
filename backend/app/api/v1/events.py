# Event ingest endpoints.
from datetime import datetime, timezone
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, ConfigDict, Field

from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.ingest_event_service import IngestEventService
from app.config import Settings
from app.dependencies import get_ingest_event_service, get_ingest_key_service, get_redis_client, get_settings
from app.domain.models.event import Event
from app.infrastructure.redis.redis_client import RedisClient
from app.logger import get_logger
from app.security.ingest_keys import hash_key, normalize_ingest_key

logger = get_logger(__name__)
router = APIRouter()


class EventRequestIn(BaseModel):
    # Nested request payload tokens.
    model_config = ConfigDict(extra="ignore")

    input_tokens: int | None = None
    endpoint: str | None = None
    feature: str | None = None


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


def _idempotency_key(project_id: str, idempotency_key: str) -> str:
    # Build Redis idempotency key with hashed input key.
    return f"idem:{project_id}:{hash_key(idempotency_key)}"


def _rate_limit_key(ingest_key: str, window_epoch_minute: int) -> str:
    # Build Redis rate-limit key for the current minute window.
    return f"rl:{hash_key(ingest_key)}:{window_epoch_minute}"


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def ingest_event(
    payload: EventIn,
    service: IngestEventService = Depends(get_ingest_event_service),
    ingest_key_service: IngestKeyService = Depends(get_ingest_key_service),
    redis_client: RedisClient = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
    ingest_key: str | None = Header(default=None, alias="X-Project-Ingest-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, str]:
    # Receive an SDK event and delegate processing to application services.
    try:
        normalized_ingest_key = normalize_ingest_key(ingest_key or "")
        if not normalized_ingest_key:
            raise HTTPException(status_code=401, detail="missing ingest key")
        project_id = ingest_key_service.resolve_project_id(
            normalized_ingest_key,
            allow_unowned_project=settings.ingest_allow_unowned_project,
        )
        if project_id is None:
            raise HTTPException(status_code=401, detail="invalid ingest key")

        if idempotency_key:
            try:
                accepted = redis_client.set_nx_ex(
                    _idempotency_key(project_id=project_id, idempotency_key=idempotency_key),
                    "1",
                    settings.idempotency_ttl_seconds,
                )
                if not accepted:
                    logger.info(
                        "Duplicate ingest skipped by idempotency key",
                        extra={"project_id": project_id},
                    )
                    return {"status": "accepted"}
            except Exception:
                logger.warning("Idempotency Redis unavailable; processing ingest in fail-open mode")

        try:
            rate_limit_window_seconds = max(int(settings.rate_limit_window_seconds), 1)
            window_epoch_minute = int(time.time()) // rate_limit_window_seconds
            rate_limit_counter = redis_client.incr(
                _rate_limit_key(ingest_key=normalized_ingest_key, window_epoch_minute=window_epoch_minute)
            )
            if rate_limit_counter == 1:
                redis_client.expire(
                    _rate_limit_key(ingest_key=normalized_ingest_key, window_epoch_minute=window_epoch_minute),
                    rate_limit_window_seconds,
                )
            if rate_limit_counter > settings.ingest_rate_limit_per_minute:
                raise HTTPException(status_code=429, detail="rate limit exceeded")
        except HTTPException:
            raise
        except Exception:
            logger.warning("Rate-limit Redis unavailable; processing ingest in fail-open mode")

        # normalize token values from payload
        input_tokens, output_tokens, total_tokens = _resolve_tokens(payload)

        # build the domain event object
        event = Event(
            id=str(uuid4()),
            ts=payload.ts,
            project_id=project_id,
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
            request_endpoint=(payload.request.endpoint if payload.request is not None else None),
            request_feature=(payload.request.feature if payload.request is not None else None),
            created_at=datetime.now(timezone.utc),
        )

        # execute ingest use-case
        service.ingest(event)
        logger.info("Event accepted", extra={"project_id": project_id, "provider": payload.provider})
        return {"status": "accepted"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Event ingest failed", extra={"project_id": ingest_key})
        raise HTTPException(status_code=500, detail="Failed to ingest event")
