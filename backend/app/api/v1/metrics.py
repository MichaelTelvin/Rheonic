# Metrics endpoints.
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.application.services.metrics_service import MetricsService
from app.application.services.project_service import ProjectService
from app.dependencies import get_current_user, get_metrics_service, get_project_service
from app.domain.models.user import User
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class ProtectMetricsOut(BaseModel):
    # Protect action counters for dashboard visibility.
    allowed_60m: int
    warned_60m: int
    blocked_60m: int
    decision_timeouts_60m: int
    last: dict[str, str] | None
    decision_latency_p50_60m_ms: int | None
    decision_latency_p95_60m_ms: int | None


class ProtectHealthOut(BaseModel):
    # Protect preflight health metrics for dashboard visibility.
    p50_ms: int | None
    p95_ms: int | None
    timeouts_60m: int


@router.get("/realtime")
def get_realtime_metrics(
    project_id: str = Query(..., min_length=1),
    service: MetricsService = Depends(get_metrics_service),
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    # Return project realtime counters from Redis.
    try:
        project_service.ensure_project_owned_by_user(project_id=project_id, user_id=current_user.id)
        metrics = service.get_realtime(project_id=project_id)
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
    service: MetricsService = Depends(get_metrics_service),
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> ProtectMetricsOut:
    # Return protect-mode warn/block counters for one project.
    try:
        project_service.ensure_project_owned_by_user(project_id=project_id, user_id=current_user.id)
        metrics = service.get_protect_metrics(project_id=project_id)
        return ProtectMetricsOut(
            allowed_60m=metrics["allowed_60m"],
            warned_60m=metrics["warned_60m"],
            blocked_60m=metrics["blocked_60m"],
            decision_timeouts_60m=metrics["decision_timeouts_60m"],
            last=metrics["last"],
            decision_latency_p50_60m_ms=metrics["decision_latency_p50_60m_ms"],
            decision_latency_p95_60m_ms=metrics["decision_latency_p95_60m_ms"],
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch protect metrics", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to fetch protect metrics")


@router.get("/protect/health", response_model=ProtectHealthOut)
def get_protect_health(
    project_id: str = Query(..., min_length=1),
    service: MetricsService = Depends(get_metrics_service),
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> ProtectHealthOut:
    # Return protect preflight health metrics (latency + timeouts) for one project.
    try:
        project_service.ensure_project_owned_by_user(project_id=project_id, user_id=current_user.id)
        metrics = service.get_protect_health(project_id=project_id)
        return ProtectHealthOut(
            p50_ms=int(metrics["p50_ms"]) if isinstance(metrics.get("p50_ms"), int) else None,
            p95_ms=int(metrics["p95_ms"]) if isinstance(metrics.get("p95_ms"), int) else None,
            timeouts_60m=int(metrics.get("timeouts_60m", 0)),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch protect health", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to fetch protect health")
