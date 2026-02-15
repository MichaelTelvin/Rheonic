"""Aggregate API routers."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.events import router as events_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.policy import router as policy_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/v1/auth", tags=["auth"])
api_router.include_router(events_router, prefix="/v1/events", tags=["events"])
api_router.include_router(incidents_router, prefix="/v1/incidents", tags=["incidents"])
api_router.include_router(metrics_router, prefix="/v1/metrics", tags=["metrics"])
api_router.include_router(policy_router, prefix="/v1/policy", tags=["policy"])
