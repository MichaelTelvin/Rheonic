# Concrete project repository implementation.
from datetime import datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.application.interfaces.project_repository import ProjectRepository
from app.config import Settings
from app.domain.models.project import Project
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import EventRecord, IncidentRecord, IngestKeyRecord, ProjectModelRecord, ProjectRecord
from app.logger import get_logger

logger = get_logger(__name__)


class ProjectRepositoryImpl(ProjectRepository):
    # Database-backed implementation for projects.

    def __init__(self, session_factory: DatabaseSessionFactory) -> None:
        # Initialize repository dependencies.
        self._session_factory = session_factory
        self._settings = Settings()

    def list_projects(self) -> list[Project]:
        # Return all projects ordered by creation time.
        try:
            with self._session_factory.create_session() as session:
                records = session.query(ProjectRecord).order_by(ProjectRecord.created_at.asc()).all()
            return [_to_domain(record, settings=self._settings) for record in records]
        except Exception:
            logger.exception("Failed listing projects")
            raise

    def list_projects_for_user(self, user_id: str) -> list[Project]:
        # Return user-owned projects ordered by creation time.
        try:
            with self._session_factory.create_session() as session:
                records = (
                    session.query(ProjectRecord)
                    .filter(ProjectRecord.user_id == user_id)
                    .order_by(ProjectRecord.created_at.asc())
                    .all()
                )
            return [_to_domain(record, settings=self._settings) for record in records]
        except Exception:
            logger.exception("Failed listing projects for user", extra={"user_id": user_id})
            raise

    def get_project(self, project_id: str) -> Project | None:
        # Return a single project by id.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
            if record is None:
                return None
            return _to_domain(record, settings=self._settings)
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
                    user_id=project.user_id,
                    protect_enabled=project.protect_enabled,
                    protect_fail_mode=project.protect_fail_mode,
                    apply_clamp=project.apply_clamp,
                    protect_max_req_per_min=project.protect_max_req_per_min,
                    protect_max_tok_per_min=project.protect_max_tok_per_min,
                    created_at=project.created_at,
                )
                session.add(record)
                session.commit()
            logger.info("Project created", extra={"project_id": project.id})
            return project
        except Exception:
            logger.exception("Failed creating project", extra={"project_id": project.id})
            raise

    def get_project_by_name(self, name: str) -> Project | None:
        # Return a single project by exact name.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(ProjectRecord).filter(ProjectRecord.name == name).first()
            return _to_domain(record, settings=self._settings) if record is not None else None
        except Exception:
            logger.exception("Failed fetching project by name", extra={"name": name})
            raise

    def get_project_by_name_for_user(self, name: str, user_id: str) -> Project | None:
        # Return a single project by exact name scoped to a user.
        try:
            with self._session_factory.create_session() as session:
                record = (
                    session.query(ProjectRecord)
                    .filter(ProjectRecord.name == name)
                    .filter(ProjectRecord.user_id == user_id)
                    .first()
                )
            return _to_domain(record, settings=self._settings) if record is not None else None
        except Exception:
            logger.exception("Failed fetching project by name for user", extra={"name": name, "user_id": user_id})
            raise

    def update_project_protect_settings(
        self,
        project_id: str,
        protect_enabled: bool,
        protect_fail_mode: str,
        apply_clamp: bool,
        protect_max_req_per_min: int | None,
        protect_max_tok_per_min: int | None,
    ) -> Project | None:
        # Update and return project protect settings.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
                if record is None:
                    return None
                record.protect_enabled = protect_enabled
                record.protect_fail_mode = protect_fail_mode
                record.apply_clamp = apply_clamp
                record.protect_max_req_per_min = protect_max_req_per_min
                record.protect_max_tok_per_min = protect_max_tok_per_min
                session.add(record)
                session.commit()
                session.refresh(record)
            return _to_domain(record, settings=self._settings)
        except Exception:
            logger.exception("Failed updating project protect settings", extra={"project_id": project_id})
            raise

    def update_project_webhook_settings(
        self,
        project_id: str,
        webhook_enabled: bool,
        email_enabled: bool,
        webhook_url: str | None,
    ) -> Project | None:
        # Update and return project webhook settings.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
                if record is None:
                    return None
                record.webhook_enabled = webhook_enabled
                record.email_enabled = email_enabled
                record.webhook_url = webhook_url
                session.add(record)
                session.commit()
                session.refresh(record)
            return _to_domain(record, settings=self._settings)
        except Exception:
            logger.exception("Failed updating project webhook settings", extra={"project_id": project_id})
            raise

    def record_project_model_first_seen(
        self,
        *,
        project_id: str,
        provider: str,
        model: str,
        first_seen_at: datetime,
    ) -> bool:
        # Insert first-seen provider/model tuple for project; ignore duplicates from retries/races.
        try:
            with self._session_factory.create_session() as session:
                record = ProjectModelRecord(
                    id=str(uuid4()),
                    project_id=project_id,
                    provider=provider,
                    model=model,
                    first_seen_at=first_seen_at,
                )
                session.add(record)
                session.commit()
                return True
        except IntegrityError:
            return False
        except Exception:
            logger.exception(
                "Failed recording project model first seen",
                extra={"project_id": project_id, "provider": provider, "model": model},
            )
            raise

    def count_project_models(self, project_id: str) -> int:
        # Count distinct provider/model rows tracked for a project.
        try:
            with self._session_factory.create_session() as session:
                return int(
                    session.query(ProjectModelRecord).filter(ProjectModelRecord.project_id == project_id).count()
                )
        except Exception:
            logger.exception("Failed counting project models", extra={"project_id": project_id})
            raise

    def list_project_providers(self, project_id: str) -> list[str]:
        # List distinct providers seen for project models.
        try:
            with self._session_factory.create_session() as session:
                rows = (
                    session.query(ProjectModelRecord.provider)
                    .filter(ProjectModelRecord.project_id == project_id)
                    .distinct()
                    .order_by(ProjectModelRecord.provider.asc())
                    .all()
                )
            return [str(provider) for (provider,) in rows if provider]
        except Exception:
            logger.exception("Failed listing project providers", extra={"project_id": project_id})
            raise

    def delete_project(self, project_id: str) -> bool:
        # Delete one project and associated scoped rows.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
                if record is None:
                    return False
                session.query(EventRecord).filter(EventRecord.project_id == project_id).delete(
                    synchronize_session=False
                )
                session.query(IncidentRecord).filter(IncidentRecord.project_id == project_id).delete(
                    synchronize_session=False
                )
                session.query(IngestKeyRecord).filter(IngestKeyRecord.project_id == project_id).delete(
                    synchronize_session=False
                )
                session.query(ProjectModelRecord).filter(ProjectModelRecord.project_id == project_id).delete(
                    synchronize_session=False
                )
                session.delete(record)
                session.commit()
                return True
        except Exception:
            logger.exception("Failed deleting project", extra={"project_id": project_id})
            raise


def _to_domain(record: ProjectRecord, settings: Settings | None = None) -> Project:
    # Convert SQLAlchemy project record to domain model.
    return Project(
        id=record.id,
        name=record.name,
        user_id=record.user_id,
        created_at=record.created_at,
        protect_enabled=bool(getattr(record, "protect_enabled", False)),
        protect_fail_mode=str(getattr(record, "protect_fail_mode", "open") or "open"),
        apply_clamp=bool(getattr(record, "apply_clamp", False)),
        protect_max_req_per_min=getattr(record, "protect_max_req_per_min", None),
        protect_max_tok_per_min=getattr(record, "protect_max_tok_per_min", None),
        webhook_enabled=bool(getattr(record, "webhook_enabled", False)),
        email_enabled=bool(getattr(record, "email_enabled", False)),
        webhook_url=getattr(record, "webhook_url", None),
    )
