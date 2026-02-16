# Domain model for incidents.
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Incident:
    # Represents a detected anomaly incident.
    id: str
    project_id: str
    incident_type: str
    severity: str
    status: str
    created_at: datetime
    resolved_at: datetime | None
    evidence: dict[str, object]
