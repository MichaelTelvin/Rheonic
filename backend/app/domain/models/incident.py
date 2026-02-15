"""Domain model for incidents."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Incident:
    """Represents a detected anomaly incident."""

    id: str
    project_id: str
    incident_type: str
    severity: str
    created_at: datetime
    evidence: dict[str, object]
