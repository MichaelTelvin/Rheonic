# Metrics endpoints.
from fastapi import APIRouter, Depends, HTTPException, Query

from app.application.services.metrics_service import MetricsService
from app.dependencies import get_metrics_service
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/realtime")
def get_realtime_metrics(
    project_id: str = Query(..., min_length=1),
    service: MetricsService = Depends(get_metrics_service),
) -> dict[str, int]:
    # Return project realtime counters from Redis.
    try:
        metrics = service.get_realtime(project_id=project_id)
        logger.debug("Realtime metrics fetched", extra={"project_id": project_id})
        return metrics
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch realtime metrics", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to fetch realtime metrics")
