# Concrete project repository implementation.
from app.application.interfaces.project_repository import ProjectRepository
from app.domain.models.project import Project
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import ProjectRecord
from app.logger import get_logger

logger = get_logger(__name__)


class ProjectRepositoryImpl(ProjectRepository):
    # Database-backed implementation for projects.

    def __init__(self, session_factory: DatabaseSessionFactory) -> None:
        # Initialize repository dependencies.
        self._session_factory = session_factory

    def list_projects(self) -> list[Project]:
        # Return all projects ordered by creation time.
        try:
            with self._session_factory.create_session() as session:
                records = session.query(ProjectRecord).order_by(ProjectRecord.created_at.asc()).all()
            return [_to_domain(record) for record in records]
        except Exception:
            logger.exception("Failed listing projects")
            raise

    def get_project(self, project_id: str) -> Project | None:
        # Return a single project by id.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
            if record is None:
                return None
            return _to_domain(record)
        except Exception:
            logger.exception("Failed fetching project", extra={"project_id": project_id})
            raise

    def create_project(self, project: Project) -> Project:
        # Persist a new project row.
        try:
            with self._session_factory.create_session() as session:
                record = ProjectRecord(
                    id=project.id,
                    name=project.name,
                    created_at=project.created_at,
                )
                session.add(record)
                session.commit()
            logger.info("Project created", extra={"project_id": project.id})
            return project
        except Exception:
            logger.exception("Failed creating project", extra={"project_id": project.id})
            raise


def _to_domain(record: ProjectRecord) -> Project:
    # Convert SQLAlchemy project record to domain model.
    return Project(
        id=record.id,
        name=record.name,
        created_at=record.created_at,
    )
