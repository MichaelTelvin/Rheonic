# Password hashing utilities.
import bcrypt


def hash_password(plain: str) -> str:
    # Hash password using bcrypt.
    hashed = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    # Verify password against hash.
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
