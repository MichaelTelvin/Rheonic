"""Domain model for provider pricing entries."""

from dataclasses import dataclass


@dataclass(slots=True)
class Pricing:
    """Represents token pricing for a model/provider combination."""

    provider: str
    model: str
    input_cost_per_1k: float
    output_cost_per_1k: float
