# Money value object.
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Money:
    # Represents a monetary amount in a fixed currency.
    amount: float
    currency: str = "USD"
