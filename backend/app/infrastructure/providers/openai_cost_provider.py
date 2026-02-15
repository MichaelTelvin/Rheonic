"""OpenAI cost provider scaffold."""

from app.application.interfaces.cost_provider import CostProvider


class OpenAICostProvider(CostProvider):
    """Calculates cost estimates for OpenAI usage."""

    def calculate_cost(self, usage: dict[str, object]) -> float:
        _ = usage
        # TODO: Map usage metadata to OpenAI pricing.
        return 0.0
