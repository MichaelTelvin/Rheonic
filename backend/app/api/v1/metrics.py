"""Metrics endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def get_metrics() -> dict[str, dict[str, str]]:
    """Return aggregate metrics for dashboard visualization."""
    # TODO: Wire metrics service DTOs.
    return {"data": {}}
