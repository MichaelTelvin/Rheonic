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
    warn_60m: int
    block_60m: int
    last: dict[str, str] | None


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
            warn_60m=int(metrics.get("warn_60m", 0)),
            block_60m=int(metrics.get("block_60m", 0)),
            last=metrics.get("last") if isinstance(metrics.get("last"), dict) else None,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch protect metrics", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to fetch protect metrics")
