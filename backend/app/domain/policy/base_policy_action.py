"""Policy action interface."""

from abc import ABC, abstractmethod


class BasePolicyAction(ABC):
    """Strategy interface for protect-mode actions."""

    @abstractmethod
    def apply(self, context: dict[str, object]) -> dict[str, object]:
        """Apply policy action to the decision context."""
