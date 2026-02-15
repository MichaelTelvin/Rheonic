"""Incident query endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_incidents() -> dict[str, list[dict[str, str]]]:
    """List incidents for the active project context."""
    # TODO: Wire incident query service and pagination.
    return {"items": []}
