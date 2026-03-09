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

    def list_project_providers(self, project_id: str, user_id: str) -> list[str]:
        # Return distinct providers used by one owned project.
        self.ensure_project_owned_by_user(project_id=project_id, user_id=user_id)
        return self._project_repository.list_project_providers(project_id=project_id)

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

    def get_project_protect_settings(self, project_id: str, user_id: str) -> Project:
        # Return protect settings for an owned project.
        return self.ensure_project_owned_by_user(project_id=project_id, user_id=user_id)

    def update_project_protect_settings(
        self,
        project_id: str,
        user_id: str,
        protect_enabled: bool,
        protect_fail_mode: str,
        apply_clamp: bool,
        protect_max_req_per_min: int | None,
        protect_max_tok_per_min: int | None,
    ) -> Project:
        # Update protect settings for an owned project.
        self.ensure_project_owned_by_user(project_id=project_id, user_id=user_id)
        updated = self._project_repository.update_project_protect_settings(
            project_id=project_id,
            protect_enabled=protect_enabled,
            protect_fail_mode=protect_fail_mode,
            apply_clamp=apply_clamp,
            protect_max_req_per_min=protect_max_req_per_min,
            protect_max_tok_per_min=protect_max_tok_per_min,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="project not found")
        return updated

    def get_project_webhook_settings(self, project_id: str, user_id: str) -> Project:
        # Return webhook settings for an owned project.
        return self.ensure_project_owned_by_user(project_id=project_id, user_id=user_id)

    def update_project_webhook_settings(
        self,
        project_id: str,
        user_id: str,
        webhook_enabled: bool,
        email_enabled: bool,
        webhook_url: str | None,
        webhook_secret: str | None,
    ) -> Project:
        # Update webhook configuration for owned project.
        _ = self.get_project_webhook_settings(project_id=project_id, user_id=user_id)
        updated = self._project_repository.update_project_webhook_settings(
            project_id=project_id,
            webhook_enabled=webhook_enabled,
            email_enabled=email_enabled,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="project not found")
        return updated

    def delete_project(self, project_id: str, user_id: str) -> None:
        # Delete an owned project and its scoped records.
        self.ensure_project_owned_by_user(project_id=project_id, user_id=user_id)
        deleted = self._project_repository.delete_project(project_id=project_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="project not found")
