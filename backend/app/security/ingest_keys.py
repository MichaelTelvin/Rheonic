# Ingest key generation and hashing helpers.
import hashlib
import secrets


def normalize_ingest_key(plaintext: str) -> str:
    # Normalize copied ingest key values (quotes, whitespace, optional env-style prefix).
    value = (plaintext or "").strip().strip('"').strip("'")
    if value.startswith("RHEONIC_INGEST_KEY="):
        value = value.split("=", 1)[1].strip().strip('"').strip("'")
    return value.strip()


def generate_ingest_key() -> str:
    # Generate a url-safe key suitable for header transport.
    return secrets.token_urlsafe(32)


def hash_key(plaintext: str) -> str:
    # Return sha256 hex digest for the provided plaintext key.
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def last4(plaintext: str) -> str:
    # Return trailing 4 chars for display.
    return plaintext[-4:]
