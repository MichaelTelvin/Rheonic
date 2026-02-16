# Project query endpoints.
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.application.services.project_service import ProjectService
from app.dependencies import get_project_service
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class ProjectOut(BaseModel):
    # API response model for projects.
    id: str
    name: str
    created_at: datetime


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
