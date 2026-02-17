# Domain model for projects.
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Project:
    # Represents a project available for dashboard selection.
    id: str
    name: str
    user_id: str | None
    created_at: datetime
