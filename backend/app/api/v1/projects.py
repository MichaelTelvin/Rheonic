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


class ProjectProvidersOut(BaseModel):
    # Distinct providers recorded for one project.
    providers: list[str]


class DeleteProjectOut(BaseModel):
    # API response model for project deletion.
    status: str


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


@router.get("/{project_id}/providers", response_model=ProjectProvidersOut)
def list_project_providers(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> ProjectProvidersOut:
    # Return ordered distinct providers used by an owned project.
    try:
        providers = service.list_project_providers(project_id=project_id, user_id=current_user.id)
        return ProjectProvidersOut(providers=providers)
    except HTTPException:
        raise
    except Exception:
        logger.exception("List project providers endpoint failed", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to list project providers")


@router.delete("/{project_id}", response_model=DeleteProjectOut)
def delete_project(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> DeleteProjectOut:
    # Delete one owned project and scoped records.
    try:
        service.delete_project(project_id=project_id, user_id=current_user.id)
        return DeleteProjectOut(status="deleted")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Delete project endpoint failed", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Failed to delete project")
