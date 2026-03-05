from dataclasses import dataclass
from datetime import datetime
from typing import Literal

TransportKind = Literal["webhook", "email"]
TransportStatus = Literal["pending", "sending", "delivered", "failed", "dead"]


@dataclass(slots=True)
class TransportOutbox:
    id: str
    project_id: str
    kind: TransportKind
    event_type: str
    destination: str | None
    subject: str | None
    template: str | None
    payload: dict[str, object]
    dedupe_key: str
    status: TransportStatus
    attempts: int
    max_attempts: int
    next_attempt_at: datetime
    last_error_code: str | None
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None
    delivered_at: datetime | None
