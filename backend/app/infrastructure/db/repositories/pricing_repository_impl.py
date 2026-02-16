# Concrete pricing repository implementation scaffold.
from app.application.interfaces.pricing_repository import PricingRepository
from app.domain.models.pricing import Pricing


class PricingRepositoryImpl(PricingRepository):
    # Database-backed implementation for pricing data.
    def get_provider_pricing(self, provider: str) -> list[Pricing]:
        _ = provider
        # TODO: Return latest pricing rows for provider.
        return []
