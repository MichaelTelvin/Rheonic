# Domain model for project ingest keys.
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class IngestKey:
    # Represents an ingest key record persisted for a project.
    id: str
    project_id: str
    name: str
    key_hash: str
    last4: str | None
    status: str
    created_at: datetime
    revoked_at: datetime | None
