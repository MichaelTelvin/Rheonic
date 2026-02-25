from dataclasses import dataclass, field
from datetime import datetime

from app.domain.models.event import Event


@dataclass(frozen=True)
class Signal:
    # Detector output consumed by incident manager.
    detector: str
    scope_provider: str
    fingerprint: str
    evidence: dict[str, object]
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DetectionContext:
    # Shared detector input for one ingest or protect evaluation.
    project_id: str
    provider: str
    model: str | None
    environment: str | None
    now: datetime
    current_requests_60s: int
    current_tokens_60s: int
    req_cap: int | None
    tok_cap: int | None
    protect_enabled: bool
    estimated_next_tokens: int | None = None
    current_event: Event | None = None
    recent_events: list[Event] = field(default_factory=list)
    warn_ratio: float = 0.8
    retry_storm_window_seconds: int = 60
    retry_storm_count: int = 5
    loop_window_seconds: int = 30
    loop_count: int = 6
    token_explosion_ratio: float = 0.8
    token_explosion_abs: int = 6000
