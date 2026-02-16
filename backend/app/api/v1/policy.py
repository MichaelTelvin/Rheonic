# Protect policy endpoints.
from fastapi import APIRouter, HTTPException

from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("")
async def get_policy() -> dict[str, dict[str, str]]:
    # Fetch active project policy configuration.
    try:
        # TODO: Connect policy evaluation/configuration service.
        logger.debug("Policy endpoint called")
        return {"policy": {}}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Get policy endpoint failed")
        raise HTTPException(status_code=500, detail="Failed to fetch policy")
