# Protect mode API endpoints.
from datetime import datetime, timezone
from time import perf_counter

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field

from app.application.provider_scope import scoped_project_provider_id
from app.application.services.incident_manager import IncidentManager
from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.project_service import ProjectService
from app.application.services.protect_service import (
    ProtectDecision,
    ProtectDecisionContext,
    ProtectService,
)
from app.config import app_config
from app.dependencies import (
    get_current_user,
    get_incident_manager,
    get_ingest_key_service,
    get_project_service,
    get_protect_action_store,
    get_protect_service,
)
from app.domain.models.user import User
from app.infrastructure.redis.protect_action_store import ProtectActionStore
from app.logger import build_log_extra, get_logger

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
    model: str | None = None
    request_id: str | None = None


class DecisionUnavailableIn(BaseModel):
    # Failure report payload from SDK when preflight fails without a timeout.
    environment: str
    provider: str | None = None
    model: str | None = None
    request_id: str | None = None


@router.post("/protect/decision", response_model=ProtectDecisionOut)
def protect_decision(
    payload: ProtectDecisionIn,
    response: Response,
    background_tasks: BackgroundTasks,
    service: ProtectService = Depends(get_protect_service),
    protect_action_store: ProtectActionStore = Depends(get_protect_action_store),
    ingest_key_service: IngestKeyService = Depends(get_ingest_key_service),
    incident_manager: IncidentManager = Depends(get_incident_manager),
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
            emit_notifications=False,
        )
        if decision is None:
            raise HTTPException(status_code=401, detail="invalid ingest key")
        latency_ms = int((perf_counter() - start) * 1000)
        response.headers["X-Protect-Decision-Latency-Ms"] = str(latency_ms)
        project = ingest_key_service.resolve_project(plaintext_key=ingest_key)
        if project_id:
            scoped_id = scoped_project_provider_id(project_id, payload.provider)
            if project is not None and project.protect_enabled:
                finalized, _ = protect_action_store.finalize_outcome(
                    project_id=scoped_id,
                    decision=decision.decision,
                    reason=decision.reason,
                    source=app_config.protect_outcome_source_live,
                    request_id=request_id,
                )
                if (
                    finalized
                    and decision.decision == "block"
                    and decision.reason in {"req_cap_breach", "tok_cap_breach"}
                    and decision.blocked_until
                    and decision.retry_after_seconds is not None
                ):
                    protect_action_store.set_block_cooldown(
                        project_id=scoped_id,
                        blocked_until_ms=int(datetime.fromisoformat(decision.blocked_until).timestamp() * 1000),
                        cooldown_seconds=decision.retry_after_seconds,
                        request_id=request_id,
                    )
            else:
                finalized = False
            protect_action_store.record_health(
                project_id=scoped_id,
                latency_ms=latency_ms,
            )
            if project is not None and project.protect_enabled and finalized:
                background_tasks.add_task(
                    _postprocess_live_preflight_decision,
                    service=service,
                    incident_manager=incident_manager,
                    project_id=project_id,
                    payload=payload,
                    decision=decision,
                    request_id=request_id,
                    latency_ms=latency_ms,
                )
        logger.info(
            "Protect decision evaluated",
            extra=build_log_extra(
                event="protect_action",
                metadata={
                    "project_id": project_id,
                    "provider": payload.provider,
                    "model": payload.model,
                    "environment": payload.environment,
                    "request_id": request_id,
                    "decision": decision.decision,
                    "reason": decision.reason,
                    "finalized": finalized,
                    "latency_ms": latency_ms,
                },
            ),
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
        logger.exception("Protect decision endpoint failed", extra=build_log_extra(event="error"))
        raise HTTPException(status_code=500, detail="Failed to evaluate protect decision")


@router.post("/protect/decision-timeout", status_code=202)
def protect_decision_timeout(
    payload: DecisionTimeoutIn,
    ingest_key_service: IngestKeyService = Depends(get_ingest_key_service),
    protect_action_store: ProtectActionStore = Depends(get_protect_action_store),
    protect_service: ProtectService = Depends(get_protect_service),
    incident_manager: IncidentManager = Depends(get_incident_manager),
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
        provider = payload.provider or "unknown"
        resolved_request_id = request_id_header or payload.request_id
        fallback_decision = "block" if project.protect_fail_mode == "closed" else "allow"
        finalized, replaced = protect_action_store.finalize_outcome(
            project_id=scoped_project_provider_id(project.id, provider),
            decision=fallback_decision,
            reason="decision_timeout",
            source=app_config.protect_outcome_source_timeout_fallback,
            request_id=resolved_request_id,
        )
        if (
            finalized
            and fallback_decision == "allow"
            and replaced is not None
            and replaced.get("source") == app_config.protect_outcome_source_live
            and replaced.get("decision") == "block"
        ):
            protect_action_store.clear_block_cooldown(
                scoped_project_provider_id(project.id, provider),
                request_id=resolved_request_id,
            )
            incident_manager.reconcile_timeout_superseded_live_block(
                project_id=project.id,
                provider=provider,
                request_id=resolved_request_id,
                source=app_config.protect_outcome_source_timeout_fallback,
            )
        logger.info(
            "Protect timeout fallback recorded",
            extra=build_log_extra(
                event="protect_timeout_fallback",
                metadata={
                    "project_id": project.id,
                    "provider": provider,
                    "model": payload.model,
                    "environment": payload.environment,
                    "request_id": resolved_request_id,
                    "decision": fallback_decision,
                    "fail_mode": project.protect_fail_mode,
                    "source": app_config.protect_outcome_source_timeout_fallback,
                },
            ),
        )
        if project.protect_fail_mode == "closed":
            protect_service.report_fail_closed_block(
                project_id=project.id,
                provider=provider,
                model=payload.model,
                environment=payload.environment,
                detail_reason="decision_timeout",
                source=app_config.protect_outcome_source_timeout_fallback,
                request_id=resolved_request_id,
            )
            incident_manager.process_protect_block(
                project_id=project.id,
                provider=provider,
                model=payload.model,
                environment=payload.environment,
                now=datetime.now(timezone.utc),
                reason="fail_closed",
                requests_60s=None,
                tokens_60s=None,
                req_cap=project.protect_max_req_per_min,
                tok_cap=project.protect_max_tok_per_min,
                blocked_until=None,
                retry_after_seconds=None,
                request_id=resolved_request_id,
                source=app_config.protect_outcome_source_timeout_fallback,
            )
        return {"status": "accepted"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Protect decision-timeout endpoint failed", extra=build_log_extra(event="error"))
        raise HTTPException(status_code=500, detail="Failed to record decision timeout")


@router.post("/protect/decision-unavailable", status_code=202)
def protect_decision_unavailable(
    payload: DecisionUnavailableIn,
    ingest_key_service: IngestKeyService = Depends(get_ingest_key_service),
    protect_action_store: ProtectActionStore = Depends(get_protect_action_store),
    protect_service: ProtectService = Depends(get_protect_service),
    incident_manager: IncidentManager = Depends(get_incident_manager),
    ingest_key: str | None = Header(default=None, alias="X-Project-Ingest-Key"),
    request_id_header: str | None = Header(default=None, alias="X-Rheonic-Protect-Request-Id"),
) -> dict[str, str]:
    # Record one SDK-side preflight unavailable fallback for the project mapped from ingest key.
    _ = payload
    try:
        if not ingest_key:
            raise HTTPException(status_code=401, detail="missing ingest key")
        project = ingest_key_service.resolve_project(plaintext_key=ingest_key)
        if project is None:
            raise HTTPException(status_code=401, detail="invalid ingest key")
        provider = payload.provider or "unknown"
        resolved_request_id = request_id_header or payload.request_id
        fallback_decision = "block" if project.protect_fail_mode == "closed" else "allow"
        finalized, replaced = protect_action_store.finalize_outcome(
            project_id=scoped_project_provider_id(project.id, provider),
            decision=fallback_decision,
            reason="decision_unavailable",
            source=app_config.protect_outcome_source_unavailable_fallback,
            request_id=resolved_request_id,
        )
        if (
            finalized
            and fallback_decision == "allow"
            and replaced is not None
            and replaced.get("source") == app_config.protect_outcome_source_live
            and replaced.get("decision") == "block"
        ):
            protect_action_store.clear_block_cooldown(
                scoped_project_provider_id(project.id, provider),
                request_id=resolved_request_id,
            )
            incident_manager.reconcile_timeout_superseded_live_block(
                project_id=project.id,
                provider=provider,
                request_id=resolved_request_id,
                source=app_config.protect_outcome_source_unavailable_fallback,
            )
        logger.info(
            "Protect unavailable fallback recorded",
            extra=build_log_extra(
                event="protect_unavailable_fallback",
                metadata={
                    "project_id": project.id,
                    "provider": provider,
                    "model": payload.model,
                    "environment": payload.environment,
                    "request_id": resolved_request_id,
                    "decision": fallback_decision,
                    "fail_mode": project.protect_fail_mode,
                    "source": app_config.protect_outcome_source_unavailable_fallback,
                },
            ),
        )
        if project.protect_fail_mode == "closed":
            protect_service.report_fail_closed_block(
                project_id=project.id,
                provider=provider,
                model=payload.model,
                environment=payload.environment,
                detail_reason="decision_unavailable",
                source=app_config.protect_outcome_source_unavailable_fallback,
                request_id=resolved_request_id,
            )
            incident_manager.process_protect_block(
                project_id=project.id,
                provider=provider,
                model=payload.model,
                environment=payload.environment,
                now=datetime.now(timezone.utc),
                reason="fail_closed",
                requests_60s=None,
                tokens_60s=None,
                req_cap=project.protect_max_req_per_min,
                tok_cap=project.protect_max_tok_per_min,
                blocked_until=None,
                retry_after_seconds=None,
                request_id=resolved_request_id,
                source=app_config.protect_outcome_source_unavailable_fallback,
            )
        return {"status": "accepted"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Protect decision-unavailable endpoint failed", extra=build_log_extra(event="error"))
        raise HTTPException(status_code=500, detail="Failed to record decision unavailable fallback")


def _record_preflight_incident_if_needed(
    *,
    incident_manager: IncidentManager,
    project_id: str,
    payload: ProtectDecisionIn,
    decision: ProtectDecision,
    request_id: str | None = None,
) -> None:
    if decision.decision != "block" or decision.reason not in {"req_cap_breach", "tok_cap_breach", "cooldown_active"}:
        return
    snapshot = decision.snapshot or {}
    incident_manager.process_protect_block(
        project_id=project_id,
        provider=payload.provider,
        model=payload.model,
        environment=payload.environment,
        now=datetime.now(timezone.utc),
        reason=decision.reason,
        requests_60s=_safe_int(snapshot.get("requests_60s")),
        tokens_60s=_safe_int(snapshot.get("tokens_60s")),
        req_cap=_safe_int(snapshot.get("threshold_req_60s")),
        tok_cap=_safe_int(snapshot.get("threshold_tok_60s")),
        blocked_until=decision.blocked_until,
        retry_after_seconds=decision.retry_after_seconds,
        request_id=request_id,
        source=app_config.protect_outcome_source_live,
    )


def _postprocess_live_preflight_decision(
    *,
    service: ProtectService,
    incident_manager: IncidentManager,
    project_id: str,
    payload: ProtectDecisionIn,
    decision: ProtectDecision,
    request_id: str | None,
    latency_ms: int,
) -> None:
    should_emit_notifications = latency_ms <= max(int(decision.decision_timeout_ms), 0)
    snapshot = decision.snapshot or {}
    requests_60s = _safe_int(snapshot.get("requests_60s"))
    tokens_60s = _safe_int(snapshot.get("tokens_60s"))
    req_cap = _safe_int(snapshot.get("threshold_req_60s"))
    tok_cap = _safe_int(snapshot.get("threshold_tok_60s"))
    scoped_id = scoped_project_provider_id(project_id, payload.provider)

    if should_emit_notifications:
        if decision.decision == "block" and decision.reason in {"req_cap_breach", "tok_cap_breach"}:
            service.enqueue_live_block_notifications(
                project_id=project_id,
                provider=payload.provider,
                model=payload.model,
                environment=payload.environment,
                detail_reason=decision.reason,
                requests_60s=requests_60s or 0,
                tokens_60s=tokens_60s or 0,
                max_req=req_cap,
                max_tok=tok_cap,
                blocked_until=decision.blocked_until,
                retry_after_seconds=decision.retry_after_seconds,
                source=app_config.protect_outcome_source_live,
            )
        elif (
            decision.decision == "block"
            and decision.reason == "cooldown_active"
            and decision.blocked_until
            and decision.retry_after_seconds is not None
        ):
            service.enqueue_live_cooldown_block_if_needed(
                project_id=project_id,
                scoped_id=scoped_id,
                provider=payload.provider,
                model=payload.model,
                environment=payload.environment,
                requests_60s=requests_60s or 0,
                tokens_60s=tokens_60s or 0,
                max_req=req_cap,
                max_tok=tok_cap,
                blocked_until=decision.blocked_until,
                retry_after_seconds=decision.retry_after_seconds,
            )
        elif decision.decision == "clamp" and decision.reason == "token_clamp":
            predictive = snapshot.get("predictive")
            estimated_next_tokens = None
            if isinstance(predictive, dict):
                estimated_next_tokens = _safe_int(predictive.get("estimated_next_tokens"))
            service.enqueue_live_clamp_started_notifications(
                project_id=project_id,
                scoped_id=scoped_id,
                provider=payload.provider,
                model=payload.model,
                environment=payload.environment,
                requests_60s=requests_60s or 0,
                tokens_60s=tokens_60s or 0,
                max_req=req_cap,
                max_tok=tok_cap,
                estimated_next_tokens=estimated_next_tokens,
                clamp=decision.clamp,
            )

    _record_preflight_incident_if_needed(
        incident_manager=incident_manager,
        project_id=project_id,
        payload=payload,
        decision=decision,
        request_id=request_id,
    )


def _safe_int(value: object) -> int | None:
    try:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float, str)):
            return int(value)
        return None
    except (TypeError, ValueError):
        return None


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
