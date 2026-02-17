# Project query endpoints.
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.application.services.project_service import ProjectService
from app.config import Settings
from app.dependencies import get_project_service, get_settings
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class ProjectOut(BaseModel):
    # API response model for projects.
    id: str
    name: str
    created_at: datetime


class CreateProjectIn(BaseModel):
    # API request model for project creation.
    name: str


@router.get("", response_model=list[ProjectOut])
def list_projects(
    service: ProjectService = Depends(get_project_service),
) -> list[ProjectOut]:
    # List projects for selector population.
    try:
        projects = service.list_projects()
        logger.debug("Projects list endpoint called", extra={"count": len(projects)})
        return [
            ProjectOut(
                id=project.id,
                name=project.name,
                created_at=project.created_at,
            )
            for project in projects
        ]
    except HTTPException:
        raise
    except Exception:
        logger.exception("List projects endpoint failed")
        raise HTTPException(status_code=500, detail="Failed to list projects")


@router.post("", response_model=ProjectOut)
def create_project(
    payload: CreateProjectIn,
    service: ProjectService = Depends(get_project_service),
    settings: Settings = Depends(get_settings),
) -> ProjectOut:
    # Create a new project in dev-only management mode.
    try:
        if settings.app_env != "dev":
            raise HTTPException(status_code=403, detail="not enabled")
        project = service.create_project(name=payload.name)
        return ProjectOut(id=project.id, name=project.name, created_at=project.created_at)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Create project endpoint failed")
        raise HTTPException(status_code=500, detail="Failed to create project")
