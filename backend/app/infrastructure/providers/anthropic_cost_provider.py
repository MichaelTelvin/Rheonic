"""Anthropic cost provider scaffold."""

from app.application.interfaces.cost_provider import CostProvider


class AnthropicCostProvider(CostProvider):
    """Calculates cost estimates for Anthropic usage."""

    def calculate_cost(self, usage: dict[str, object]) -> float:
        _ = usage
        # TODO: Map usage metadata to Anthropic pricing.
        return 0.0
