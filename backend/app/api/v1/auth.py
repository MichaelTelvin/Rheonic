# Authentication endpoints.
from fastapi import APIRouter, HTTPException

from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/login")
async def login() -> dict[str, str]:
    # Authenticate a user and issue access credentials.
    try:
        # TODO: Add auth provider integration and token issuance.
        logger.info("Login endpoint called")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Login endpoint failed")
        raise HTTPException(status_code=500, detail="Login failed")
