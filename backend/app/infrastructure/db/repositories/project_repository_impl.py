# Concrete project repository implementation.
from datetime import datetime

from app.application.interfaces.project_repository import ProjectRepository
from app.config import Settings
from app.domain.models.project import Project
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import ProjectRecord
from app.logger import get_logger
from app.security.webhook_secrets import decrypt_webhook_secret, encrypt_webhook_secret

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
                    protect_max_req_per_min=project.protect_max_req_per_min,
                    protect_max_tok_per_min=project.protect_max_tok_per_min,
                    protect_decision_timeout_ms=project.protect_decision_timeout_ms,
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
        protect_max_req_per_min: int | None,
        protect_max_tok_per_min: int | None,
        protect_decision_timeout_ms: int,
    ) -> Project | None:
        # Update and return project protect settings.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
                if record is None:
                    return None
                record.protect_enabled = protect_enabled
                record.protect_fail_mode = protect_fail_mode
                record.protect_max_req_per_min = protect_max_req_per_min
                record.protect_max_tok_per_min = protect_max_tok_per_min
                record.protect_decision_timeout_ms = protect_decision_timeout_ms
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
        webhook_url: str | None,
        webhook_secret: str | None,
    ) -> Project | None:
        # Update and return project webhook settings.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
                if record is None:
                    return None
                record.webhook_enabled = webhook_enabled
                record.webhook_url = webhook_url
                record.webhook_secret = (
                    encrypt_webhook_secret(webhook_secret, settings=self._settings) if webhook_secret is not None else None
                )
                session.add(record)
                session.commit()
                session.refresh(record)
            return _to_domain(record, settings=self._settings)
        except Exception:
            logger.exception("Failed updating project webhook settings", extra={"project_id": project_id})
            raise

    def update_project_webhook_delivery_status(
        self,
        project_id: str,
        status: str,
        at: datetime,
        error: str | None,
    ) -> Project | None:
        # Update and return project webhook delivery status fields.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
                if record is None:
                    return None
                record.webhook_last_status = status
                record.webhook_last_at = at
                record.webhook_last_error = error
                session.add(record)
                session.commit()
                session.refresh(record)
            return _to_domain(record, settings=self._settings)
        except Exception:
            logger.exception("Failed updating project webhook delivery status", extra={"project_id": project_id})
            raise


def _to_domain(record: ProjectRecord, settings: Settings | None = None) -> Project:
    # Convert SQLAlchemy project record to domain model.
    resolved_settings = settings or Settings()
    return Project(
        id=record.id,
        name=record.name,
        user_id=record.user_id,
        created_at=record.created_at,
        protect_enabled=bool(getattr(record, "protect_enabled", False)),
        protect_fail_mode=str(getattr(record, "protect_fail_mode", "open") or "open"),
        protect_max_req_per_min=getattr(record, "protect_max_req_per_min", None),
        protect_max_tok_per_min=getattr(record, "protect_max_tok_per_min", None),
        protect_decision_timeout_ms=int(getattr(record, "protect_decision_timeout_ms", 100) or 100),
        webhook_enabled=bool(getattr(record, "webhook_enabled", False)),
        webhook_url=getattr(record, "webhook_url", None),
        webhook_secret=decrypt_webhook_secret(getattr(record, "webhook_secret", None), settings=resolved_settings),
        webhook_last_status=getattr(record, "webhook_last_status", None),
        webhook_last_at=getattr(record, "webhook_last_at", None),
        webhook_last_error=getattr(record, "webhook_last_error", None),
    )
