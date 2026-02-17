# Application service for project listing.
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.application.interfaces.project_repository import ProjectRepository
from app.domain.models.project import Project
from app.logger import get_logger

logger = get_logger(__name__)


class ProjectService:
    # Handles project retrieval use-cases.

    def __init__(self, project_repository: ProjectRepository) -> None:
        # Initialize service dependencies.
        self._project_repository = project_repository

    def list_projects(self) -> list[Project]:
        # Return projects for dashboard selection.
        try:
            projects = self._project_repository.list_projects()
            logger.debug("Projects listed", extra={"count": len(projects)})
            return projects
        except Exception:
            logger.exception("Project service list failed")
            raise

    def create_project(self, name: str) -> Project:
        # Create a new project after validation and duplicate check.
        try:
            normalized_name = name.strip()
            if not normalized_name:
                raise HTTPException(status_code=422, detail="project name is required")
            if self._project_repository.get_project_by_name(normalized_name) is not None:
                raise HTTPException(status_code=409, detail="project name already exists")
            project = Project(
                id=str(uuid4()),
                name=normalized_name,
                created_at=datetime.now(timezone.utc),
            )
            created = self._project_repository.create_project(project)
            logger.info("Project created via service", extra={"project_id": created.id})
            return created
        except HTTPException:
            raise
        except Exception:
            logger.exception("Project service create failed")
            raise
