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

    @abstractmethod
    def record_baseline_snapshot(
        self,
        project_id: str,
        requests_60s: int,
        tokens_60s: int,
        max_windows: int,
    ) -> tuple[float, float]:
        # Store current window sample and return median baselines.
        raise NotImplementedError

    @abstractmethod
    def get_baseline_snapshot(self, project_id: str, max_windows: int) -> tuple[float, float]:
        # Return request/token median baselines without appending a new sample.
        raise NotImplementedError

    @abstractmethod
    def acquire_incident_lock(self, project_id: str, incident_type: str, ttl_seconds: int) -> bool:
        # Acquire incident dedupe lock with NX semantics.
        raise NotImplementedError

    @abstractmethod
    def release_incident_lock(self, project_id: str, incident_type: str) -> None:
        # Release incident dedupe lock.
        raise NotImplementedError

    @abstractmethod
    def record_incident_escalation_hit(
        self,
        project_id: str,
        incident_type: str,
        ts_unix: int,
        score: int,
        ratio: float,
        *,
        prune_before_unix: int,
        ttl_seconds: int,
    ) -> list[dict[str, float | int]]:
        # Append and prune escalation hits for a project/type key, returning retained hits.
        raise NotImplementedError
