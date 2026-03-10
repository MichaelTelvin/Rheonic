# Protect mode API endpoints.
from time import perf_counter

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field

from app.application.services.protect_service import ProtectDecisionContext, ProtectService
from app.application.provider_scope import scoped_project_provider_id
from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.project_service import ProjectService
from app.dependencies import (
    get_current_user,
    get_ingest_key_service,
    get_project_service,
    get_protect_action_store,
    get_protect_service,
)
from app.domain.models.user import User
from app.infrastructure.redis.protect_action_store import ProtectActionStore
from app.config import app_config
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class ProtectDecisionIn(BaseModel):
    # Preflight decision request payload.
    provider: str
    model: str | None = None
    environment: str | None = None
    feature: str | None = None
    max_output_tokens: int | None = None
    input_tokens_estimate: int | None = None


class ProtectDecisionOut(BaseModel):
    # Preflight decision response payload.
    decision: str
    reason: str
    fail_mode: str
    protect_decision_timeout_ms: int
    retry_after_seconds: int | None = None
    blocked_until: str | None = None
    snapshot: dict[str, int | str | bool | None | dict[str, int | bool | None]]
    apply_clamp_enabled: bool = False
    clamp: dict[str, int | bool] | None = None


class ProjectProtectOut(BaseModel):
    # Project protect settings response payload.
    protect_enabled: bool
    protect_fail_mode: str
    apply_clamp: bool
    protect_max_req_per_min: int | None
    protect_max_tok_per_min: int | None


class ProtectRuntimeConfigOut(BaseModel):
    # Runtime protect config consumed by SDK bootstrap using ingest key auth.
    protect_fail_mode: str
    protect_decision_timeout_ms: int


class ProjectProtectIn(BaseModel):
    # Project protect settings update payload.
    protect_enabled: bool
    protect_fail_mode: str = Field(pattern="^(open|closed)$")
    apply_clamp: bool = False
    protect_max_req_per_min: int | None = Field(default=None, ge=1)
    protect_max_tok_per_min: int | None = Field(default=None, ge=1)


class DecisionTimeoutIn(BaseModel):
    # Timeout report payload from SDK when decision preflight call times out.
    environment: str
    provider: str | None = None
    request_id: str | None = None


@router.post("/protect/decision", response_model=ProtectDecisionOut)
def protect_decision(
    payload: ProtectDecisionIn,
    response: Response,
    service: ProtectService = Depends(get_protect_service),
    protect_action_store: ProtectActionStore = Depends(get_protect_action_store),
    ingest_key: str | None = Header(default=None, alias="X-Project-Ingest-Key"),
    request_id: str | None = Header(default=None, alias="X-Rheonic-Protect-Request-Id"),
) -> ProtectDecisionOut:
    # Evaluate preflight decision from project protect configuration and Redis counters.
    start = perf_counter()
    try:
        if not ingest_key:
            raise HTTPException(status_code=401, detail="missing ingest key")
        project_id, decision = service.evaluate_decision(
            ingest_key=ingest_key,
            context=ProtectDecisionContext(
                max_output_tokens=payload.max_output_tokens,
                input_tokens_estimate=payload.input_tokens_estimate,
                environment=payload.environment,
                provider=payload.provider,
                model=payload.model,
                feature=payload.feature,
            ),
        )
        if decision is None:
            raise HTTPException(status_code=401, detail="invalid ingest key")
        latency_ms = int((perf_counter() - start) * 1000)
        response.headers["X-Protect-Decision-Latency-Ms"] = str(latency_ms)
        if project_id:
            scoped_id = scoped_project_provider_id(project_id, payload.provider)
            protect_action_store.finalize_outcome(
                project_id=scoped_id,
                decision=decision.decision,
                reason=decision.reason,
                source=app_config.protect_outcome_source_live,
                request_id=request_id,
            )
            protect_action_store.record_health(
                project_id=scoped_id,
                latency_ms=latency_ms,
            )
        logger.info(
            "Protect decision evaluated",
            extra={
                "project_id": project_id,
                "provider": payload.provider,
                "decision": decision.decision,
                "reason": decision.reason,
                "latency_ms": latency_ms,
            },
        )
        return ProtectDecisionOut(
            decision=decision.decision,
            reason=decision.reason,
            fail_mode=decision.fail_mode,
            protect_decision_timeout_ms=decision.decision_timeout_ms,
            retry_after_seconds=decision.retry_after_seconds,
            blocked_until=decision.blocked_until,
            snapshot=decision.snapshot,
            apply_clamp_enabled=decision.apply_clamp_enabled,
            clamp=decision.clamp,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Protect decision endpoint failed")
        raise HTTPException(status_code=500, detail="Failed to evaluate protect decision")


@router.post("/protect/decision-timeout", status_code=202)
def protect_decision_timeout(
    payload: DecisionTimeoutIn,
    ingest_key_service: IngestKeyService = Depends(get_ingest_key_service),
    protect_action_store: ProtectActionStore = Depends(get_protect_action_store),
    ingest_key: str | None = Header(default=None, alias="X-Project-Ingest-Key"),
    request_id_header: str | None = Header(default=None, alias="X-Rheonic-Protect-Request-Id"),
) -> dict[str, str]:
    # Record one SDK-side preflight timeout for the project mapped from ingest key.
    _ = payload
    try:
        if not ingest_key:
            raise HTTPException(status_code=401, detail="missing ingest key")
        project = ingest_key_service.resolve_project(plaintext_key=ingest_key)
        if project is None:
            raise HTTPException(status_code=401, detail="invalid ingest key")
        protect_action_store.finalize_outcome(
            project_id=scoped_project_provider_id(project.id, payload.provider),
            decision="block" if project.protect_fail_mode == "closed" else "allow",
            reason="decision_timeout",
            source=app_config.protect_outcome_source_timeout_fallback,
            request_id=request_id_header or payload.request_id,
        )
        return {"status": "accepted"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Protect decision-timeout endpoint failed")
        raise HTTPException(status_code=500, detail="Failed to record decision timeout")


@router.get("/protect/config", response_model=ProtectRuntimeConfigOut)
def get_protect_runtime_config(
    ingest_key_service: IngestKeyService = Depends(get_ingest_key_service),
    ingest_key: str | None = Header(default=None, alias="X-Project-Ingest-Key"),
) -> ProtectRuntimeConfigOut:
    # Return ingest-key scoped runtime protect config needed by SDK timeout fallback.
    try:
        if not ingest_key:
            raise HTTPException(status_code=401, detail="missing ingest key")
        project = ingest_key_service.resolve_project(plaintext_key=ingest_key)
        if project is None:
            raise HTTPException(status_code=401, detail="invalid ingest key")
        from app.config import Settings

        settings = Settings()
        return ProtectRuntimeConfigOut(
            protect_fail_mode=project.protect_fail_mode,
            protect_decision_timeout_ms=settings.protect_decision_timeout_ms,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Protect config endpoint failed")
        raise HTTPException(status_code=500, detail="Failed to fetch protect config")


@router.get("/projects/{project_id}/protect", response_model=ProjectProtectOut)
def get_project_protect(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> ProjectProtectOut:
    # Return protect settings for an owned project.
    try:
        project = project_service.get_project_protect_settings(project_id=project_id, user_id=current_user.id)
        return ProjectProtectOut(
            protect_enabled=project.protect_enabled,
            protect_fail_mode=project.protect_fail_mode,
            apply_clamp=project.apply_clamp,
            protect_max_req_per_min=project.protect_max_req_per_min,
            protect_max_tok_per_min=project.protect_max_tok_per_min,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Get project protect settings failed", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to fetch project protect settings")


@router.put("/projects/{project_id}/protect", response_model=ProjectProtectOut)
def update_project_protect(
    project_id: str,
    payload: ProjectProtectIn,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> ProjectProtectOut:
    # Update protect settings for an owned project.
    try:
        updated = project_service.update_project_protect_settings(
            project_id=project_id,
            user_id=current_user.id,
            protect_enabled=payload.protect_enabled,
            protect_fail_mode=payload.protect_fail_mode,
            apply_clamp=payload.apply_clamp,
            protect_max_req_per_min=payload.protect_max_req_per_min,
            protect_max_tok_per_min=payload.protect_max_tok_per_min,
        )
        return ProjectProtectOut(
            protect_enabled=updated.protect_enabled,
            protect_fail_mode=updated.protect_fail_mode,
            apply_clamp=updated.apply_clamp,
            protect_max_req_per_min=updated.protect_max_req_per_min,
            protect_max_tok_per_min=updated.protect_max_tok_per_min,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Update project protect settings failed", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to update project protect settings")
