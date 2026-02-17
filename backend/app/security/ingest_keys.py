# Ingest key generation and hashing helpers.
import hashlib
import secrets


def generate_ingest_key() -> str:
    # Generate a url-safe key suitable for header transport.
    return secrets.token_urlsafe(32)


def hash_key(plaintext: str) -> str:
    # Return sha256 hex digest for the provided plaintext key.
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def last4(plaintext: str) -> str:
    # Return trailing 4 chars for display.
    return plaintext[-4:]
