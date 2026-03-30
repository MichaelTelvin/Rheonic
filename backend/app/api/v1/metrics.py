# Metrics endpoints.
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.application.services.metrics_service import MetricsService
from app.application.services.project_service import ProjectService
from app.dependencies import get_current_user, get_metrics_service, get_project_service
from app.domain.models.user import User
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


def _metric_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    return default


def _metric_optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    return None


def _metric_last(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): str(item) for key, item in value.items()}


class ProtectMetricsOut(BaseModel):
    # Protect action counters for dashboard visibility.
    allowed_60m: int
    clamped_60m: int
    blocked_60m: int
    decision_timeouts_60m: int
    last: dict[str, str] | None
    decision_latency_p50_60m_ms: int | None
    decision_latency_p95_60m_ms: int | None


class ProtectHealthOut(BaseModel):
    # Protect preflight health metrics for dashboard visibility.
    p50_ms: int | None
    p95_ms: int | None
    timeouts_30m: int
    timeouts_60m: int


class DeliveryFailuresOut(BaseModel):
    count: int
    last_attempt_at: str | None


@router.get("/realtime")
def get_realtime_metrics(
    project_id: str = Query(..., min_length=1),
    provider: str | None = Query(None, min_length=1),
    service: MetricsService = Depends(get_metrics_service),
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    # Return project realtime counters from Redis.
    try:
        project_service.ensure_project_owned_by_user(project_id=project_id, user_id=current_user.id)
        metrics = service.get_realtime(project_id=project_id, provider=provider)
        logger.debug("Realtime metrics fetched", extra={"project_id": project_id})
        return metrics
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch realtime metrics", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to fetch realtime metrics")


@router.get("/protect", response_model=ProtectMetricsOut)
def get_protect_metrics(
    project_id: str = Query(..., min_length=1),
    provider: str | None = Query(None, min_length=1),
    service: MetricsService = Depends(get_metrics_service),
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> ProtectMetricsOut:
    # Return protect-mode allow/clamp/block counters for one project.
    try:
        project_service.ensure_project_owned_by_user(project_id=project_id, user_id=current_user.id)
        metrics = service.get_protect_metrics(project_id=project_id, provider=provider)
        return ProtectMetricsOut(
            allowed_60m=_metric_int(metrics.get("allowed_60m")),
            clamped_60m=_metric_int(metrics.get("clamped_60m")),
            blocked_60m=_metric_int(metrics.get("blocked_60m")),
            decision_timeouts_60m=_metric_int(metrics.get("decision_timeouts_60m")),
            last=_metric_last(metrics.get("last")),
            decision_latency_p50_60m_ms=_metric_optional_int(metrics.get("decision_latency_p50_60m_ms")),
            decision_latency_p95_60m_ms=_metric_optional_int(metrics.get("decision_latency_p95_60m_ms")),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch protect metrics", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to fetch protect metrics")


@router.get("/protect/health", response_model=ProtectHealthOut)
def get_protect_health(
    project_id: str = Query(..., min_length=1),
    provider: str | None = Query(None, min_length=1),
    service: MetricsService = Depends(get_metrics_service),
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> ProtectHealthOut:
    # Return protect preflight health metrics (latency + timeouts) for one project.
    try:
        project_service.ensure_project_owned_by_user(project_id=project_id, user_id=current_user.id)
        metrics = service.get_protect_health(project_id=project_id, provider=provider)
        return ProtectHealthOut(
            p50_ms=_metric_optional_int(metrics.get("p50_ms")),
            p95_ms=_metric_optional_int(metrics.get("p95_ms")),
            timeouts_30m=_metric_int(metrics.get("timeouts_30m", 0)),
            timeouts_60m=_metric_int(metrics.get("timeouts_60m", 0)),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch protect health", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to fetch protect health")


@router.get("/delivery-failures", response_model=DeliveryFailuresOut)
def get_delivery_failures(
    project_id: str = Query(..., min_length=1),
    kind: str = Query("webhook", pattern="^(webhook|email)$"),
    service: MetricsService = Depends(get_metrics_service),
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> DeliveryFailuresOut:
    try:
        project_service.ensure_project_owned_by_user(project_id=project_id, user_id=current_user.id)
        resolved_kind: Literal["webhook", "email"] = "email" if kind == "email" else "webhook"
        payload = service.get_delivery_failures(project_id=project_id, kind=resolved_kind)
        return DeliveryFailuresOut(
            count=_metric_int(payload.get("count", 0)),
            last_attempt_at=str(payload.get("last_attempt_at")) if payload.get("last_attempt_at") else None,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch delivery failures", extra={"project_id": project_id, "kind": kind})
        raise HTTPException(status_code=500, detail="Failed to fetch delivery failures")
