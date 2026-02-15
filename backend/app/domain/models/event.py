"""Domain model for SDK usage events."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Event:
    """Represents a normalized usage event from an SDK."""

    id: str
    project_id: str
    provider: str
    created_at: datetime
    input_tokens: int
    output_tokens: int
