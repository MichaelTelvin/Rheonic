"""Cache provider interface."""

from abc import ABC, abstractmethod


class CacheProvider(ABC):
    """Abstraction for protect-mode cache operations."""

    @abstractmethod
    def get(self, key: str) -> object | None:
        """Fetch cached value by key."""

    @abstractmethod
    def set(self, key: str, value: object, ttl_seconds: int) -> None:
        """Store a value with a TTL."""
