# JWT token helpers.
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt


def create_access_token(
    user_id: str,
    email: str,
    secret: str,
    algorithm: str,
    expires_minutes: int,
) -> str:
    # Build signed access token.
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str, secret: str, algorithm: str) -> dict[str, object] | None:
    # Decode and validate token payload.
    try:
        decoded = jwt.decode(token, secret, algorithms=[algorithm])
        return decoded
    except JWTError:
        return None
