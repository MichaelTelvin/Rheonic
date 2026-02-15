"""Protect policy endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def get_policy() -> dict[str, dict[str, str]]:
    """Fetch active project policy configuration."""
    # TODO: Connect policy evaluation/configuration service.
    return {"policy": {}}
