# Typed identifier value objects.
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProjectId:
    # Project identifier type wrapper.
    value: str


@dataclass(frozen=True, slots=True)
class EventId:
    # Event identifier type wrapper.
    value: str


@dataclass(frozen=True, slots=True)
class IncidentId:
    # Incident identifier type wrapper.
    value: str
