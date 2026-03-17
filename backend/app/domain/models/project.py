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
    protect_enabled: bool = False
    protect_fail_mode: str = "open"
    apply_clamp: bool = False
    protect_max_req_per_min: int | None = None
    protect_max_tok_per_min: int | None = None
    webhook_enabled: bool = False
    email_enabled: bool = False
    webhook_url: str | None = None
    webhook_payload_template_json: str | None = None
