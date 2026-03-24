from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings
from app.dependencies import get_settings
from app.health_checks import assert_critical_dependencies_ready

router = APIRouter()


@router.get("/health")
def api_health() -> dict[str, str]:
    try:
        assert_critical_dependencies_ready()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"not ready: {exc}") from exc
    return {"status": "ok"}


@router.get("/version")
def api_version(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {
        "version": settings.app_version,
        "environment": settings.app_env_normalized,
    }
