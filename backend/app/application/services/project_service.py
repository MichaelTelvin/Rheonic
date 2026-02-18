# Application service for project listing.
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.application.input_validation import sanitize_project_name
from app.application.interfaces.project_repository import ProjectRepository
from app.domain.models.project import Project
from app.logger import get_logger

logger = get_logger(__name__)


class ProjectService:
    # Handles project retrieval use-cases.

    def __init__(self, project_repository: ProjectRepository) -> None:
        # Initialize service dependencies.
        self._project_repository = project_repository

    def list_projects(self, user_id: str) -> list[Project]:
        # Return projects for dashboard selection scoped to user.
        try:
            projects = self._project_repository.list_projects_for_user(user_id=user_id)
            logger.debug("Projects listed", extra={"count": len(projects)})
            return projects
        except Exception:
            logger.exception("Project service list failed")
            raise

    def create_project(self, name: str, user_id: str) -> Project:
        # Create a new project after validation and duplicate check.
        try:
            normalized_name = sanitize_project_name(name)
            if self._project_repository.get_project_by_name_for_user(normalized_name, user_id=user_id) is not None:
                raise HTTPException(status_code=409, detail="project name already exists")
            project = Project(
                id=str(uuid4()),
                name=normalized_name,
                user_id=user_id,
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

    def ensure_project_owned_by_user(self, project_id: str, user_id: str) -> Project:
        # Verify that the project exists and is owned by user.
        project = self._project_repository.get_project(project_id)
        if project is None or project.user_id != user_id:
            raise HTTPException(status_code=404, detail="project not found")
        return project
