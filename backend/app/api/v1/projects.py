# Project query endpoints.
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.application.services.project_service import ProjectService
from app.dependencies import get_current_user, get_project_service
from app.domain.models.user import User
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
    current_user: User = Depends(get_current_user),
) -> list[ProjectOut]:
    # List projects for selector population.
    try:
        projects = service.list_projects(user_id=current_user.id)
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
    current_user: User = Depends(get_current_user),
) -> ProjectOut:
    # Create a new project for the authenticated user.
    try:
        project = service.create_project(name=payload.name, user_id=current_user.id)
        return ProjectOut(id=project.id, name=project.name, created_at=project.created_at)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Create project endpoint failed")
        raise HTTPException(status_code=500, detail="Failed to create project")
