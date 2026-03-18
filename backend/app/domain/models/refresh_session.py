from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RefreshSession:
    jti: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    replaced_by_jti: str | None
