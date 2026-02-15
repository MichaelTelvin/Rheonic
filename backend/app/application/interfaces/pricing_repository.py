"""Pricing repository interface."""

from abc import ABC, abstractmethod

from app.domain.models.pricing import Pricing


class PricingRepository(ABC):
    """Abstraction for pricing data access."""

    @abstractmethod
    def get_provider_pricing(self, provider: str) -> list[Pricing]:
        """Fetch current pricing entries for a provider."""
