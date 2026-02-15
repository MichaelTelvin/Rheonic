"""Domain model for protect policies."""

from dataclasses import dataclass


@dataclass(slots=True)
class Policy:
    """Defines deterministic protect-mode policy configuration."""

    project_id: str
    enabled: bool
    actions: list[str]
