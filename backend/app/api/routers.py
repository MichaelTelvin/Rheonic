# Aggregate API routers.
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.events import router as events_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.keys import router as keys_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.projects import router as projects_router
from app.api.v1.protect import router as protect_router
from app.api.v1.public_config import router as public_config_router
from app.api.v1.webhook import router as webhook_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/v1/auth", tags=["auth"])
api_router.include_router(events_router, prefix="/v1/events", tags=["events"])
api_router.include_router(feedback_router, prefix="/v1", tags=["feedback"])
api_router.include_router(incidents_router, prefix="/v1/incidents", tags=["incidents"])
api_router.include_router(keys_router, prefix="/v1", tags=["keys"])
api_router.include_router(metrics_router, prefix="/v1/metrics", tags=["metrics"])
api_router.include_router(protect_router, prefix="/v1", tags=["protect"])
api_router.include_router(projects_router, prefix="/v1/projects", tags=["projects"])
api_router.include_router(public_config_router, prefix="/v1", tags=["public-config"])
api_router.include_router(webhook_router, prefix="/v1", tags=["webhook"])
