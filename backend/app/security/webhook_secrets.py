# Webhook secret encryption helpers.
from __future__ import annotations

import base64
import hashlib

from app.config import Settings, app_config


def _encryption_key_bytes(settings: Settings) -> bytes:
    seed = settings.webhook_secret_encryption_key or settings.jwt_secret or app_config.webhook_secret_default_fallback_key
    return hashlib.sha256(seed.encode("utf-8")).digest()


def _xor_bytes(payload: bytes, key: bytes) -> bytes:
    # Apply a deterministic XOR stream over payload bytes.
    return bytes(byte ^ key[index % len(key)] for index, byte in enumerate(payload))


def encrypt_webhook_secret(secret: str, settings: Settings) -> str:
    # Encrypt webhook secret before persisting it.
    if not secret:
        return secret
    encrypted = _xor_bytes(secret.encode("utf-8"), _encryption_key_bytes(settings))
    token_text = base64.urlsafe_b64encode(encrypted).decode("utf-8")
    return f"{app_config.webhook_secret_prefix}{token_text}"


def decrypt_webhook_secret(secret: str | None, settings: Settings) -> str | None:
    # Decrypt stored webhook secret if it was encrypted by this service.
    if not secret:
        return None
    if not secret.startswith(app_config.webhook_secret_prefix):
        return secret
    token = secret[len(app_config.webhook_secret_prefix) :]
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8"))
        plaintext = _xor_bytes(decoded, _encryption_key_bytes(settings))
        return plaintext.decode("utf-8")
    except Exception:
        return None
