# Incident query endpoints.
from fastapi import APIRouter, HTTPException

from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("")
async def list_incidents() -> dict[str, list[dict[str, str]]]:
    # List incidents for the active project context.
    try:
        # TODO: Wire incident query service and pagination.
        logger.debug("Incidents list endpoint called")
        return {"items": []}
    except HTTPException:
        raise
    except Exception:
        logger.exception("List incidents endpoint failed")
        raise HTTPException(status_code=500, detail="Failed to list incidents")
