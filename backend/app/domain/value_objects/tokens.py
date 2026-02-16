# Token count value object.
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tokens:
    # Represents input and output token counts.
    input_tokens: int
    output_tokens: int
