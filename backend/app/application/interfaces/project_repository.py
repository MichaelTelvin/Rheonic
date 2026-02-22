# Project repository interface.
from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.models.project import Project


class ProjectRepository(ABC):
    # Abstraction for project persistence and retrieval.

    @abstractmethod
    def list_projects(self) -> list[Project]:
        # Return all projects ordered for UI selection.
        raise NotImplementedError

    @abstractmethod
    def list_projects_for_user(self, user_id: str) -> list[Project]:
        # Return projects owned by a user.
        raise NotImplementedError

    @abstractmethod
    def get_project(self, project_id: str) -> Project | None:
        # Return project by id if it exists.
        raise NotImplementedError

    @abstractmethod
    def create_project(self, project: Project) -> Project:
        # Persist a new project record.
        raise NotImplementedError

    @abstractmethod
    def get_project_by_name(self, name: str) -> Project | None:
        # Return project by exact name if it exists.
        raise NotImplementedError

    @abstractmethod
    def get_project_by_name_for_user(self, name: str, user_id: str) -> Project | None:
        # Return project by exact name scoped to user if it exists.
        raise NotImplementedError

    @abstractmethod
    def update_project_protect_settings(
        self,
        project_id: str,
        protect_enabled: bool,
        protect_fail_mode: str,
        protect_max_req_per_min: int | None,
        protect_max_tok_per_min: int | None,
        protect_decision_timeout_ms: int,
    ) -> Project | None:
        # Update and return project protect configuration.
        raise NotImplementedError

    @abstractmethod
    def update_project_webhook_settings(
        self,
        project_id: str,
        webhook_enabled: bool,
        webhook_url: str | None,
        webhook_secret: str | None,
    ) -> Project | None:
        # Update and return project webhook configuration.
        raise NotImplementedError

    @abstractmethod
    def update_project_webhook_delivery_status(
        self,
        project_id: str,
        status: str,
        at: datetime,
        error: str | None,
    ) -> Project | None:
        # Update and return latest webhook delivery status fields.
        raise NotImplementedError
