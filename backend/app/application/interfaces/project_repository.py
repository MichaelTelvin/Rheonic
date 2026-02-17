# Project repository interface.
from abc import ABC, abstractmethod

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
