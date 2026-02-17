# Domain model for users.
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class User:
    # Represents an authenticated application user.
    id: str
    email: str
    password_hash: str
    created_at: datetime
