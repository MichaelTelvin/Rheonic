# User repository interface.
from abc import ABC, abstractmethod

from app.domain.models.user import User


class UserRepository(ABC):
    # Abstraction for user persistence and lookup.

    @abstractmethod
    def get_by_id(self, user_id: str) -> User | None:
        # Return user by id.
        raise NotImplementedError

    @abstractmethod
    def get_by_email(self, email: str) -> User | None:
        # Return user by normalized email.
        raise NotImplementedError

    @abstractmethod
    def create_user(self, user: User) -> User:
        # Persist new user.
        raise NotImplementedError
