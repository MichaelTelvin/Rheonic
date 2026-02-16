# Cache provider interface.
from abc import ABC, abstractmethod


class CacheProvider(ABC):
    # Abstraction for protect-mode cache operations.

    @abstractmethod
    def get(self, key: str) -> object | None:
        # Fetch cached value by key.
        raise NotImplementedError

    @abstractmethod
    def set(self, key: str, value: object, ttl_seconds: int) -> None:
        # Store a value with a TTL.
        raise NotImplementedError


class RealtimeCounterStore(ABC):
    # Abstraction for project-scoped realtime counter operations.

    @abstractmethod
    def increment_project_60s(self, project_id: str, total_tokens: int) -> None:
        # Increment request and token counters for the project 60s window.
        raise NotImplementedError

    @abstractmethod
    def get_project_60s(self, project_id: str) -> tuple[int, int]:
        # Return request and token counters for the project 60s window.
        raise NotImplementedError
