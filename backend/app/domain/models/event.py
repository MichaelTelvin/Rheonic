# Domain model for SDK usage events.
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Event:
    # Represents a normalized usage event from an SDK.
    id: str
    ts: datetime
    project_id: str
    provider: str
    requested_model: str | None
    resolved_model: str | None
    environment: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int | None
    status: str | None
    error_type: str | None
    error_message: str | None
    http_status: int | None
    created_at: datetime
    token_explosion_tokens: int | None = None
    request_endpoint: str | None = None
    request_feature: str | None = None
    request_fingerprint: str | None = None
