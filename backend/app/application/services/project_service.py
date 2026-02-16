# Application service for project listing.
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
