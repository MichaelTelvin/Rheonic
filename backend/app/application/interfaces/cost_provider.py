"""Cost provider interface."""

from abc import ABC, abstractmethod


class CostProvider(ABC):
    """Strategy interface for provider-specific cost lookups."""

    @abstractmethod
    def calculate_cost(self, usage: dict[str, object]) -> float:
        """Calculate cost from provider usage metadata."""
