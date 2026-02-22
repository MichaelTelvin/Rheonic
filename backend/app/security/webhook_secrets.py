# Webhook secret encryption helpers.
from __future__ import annotations

import base64
import hashlib

from jose import jwe

from app.config import Settings

_ENC_PREFIX = "enc:v1:"
_DEFAULT_FALLBACK_KEY = "llmtbg-webhook-secret-default"


def _encryption_key_bytes(settings: Settings) -> bytes:
    seed = settings.webhook_secret_encryption_key or settings.jwt_secret or _DEFAULT_FALLBACK_KEY
    return hashlib.sha256(seed.encode("utf-8")).digest()


def encrypt_webhook_secret(secret: str, settings: Settings) -> str:
    # Encrypt webhook secret before persisting it.
    if not secret:
        return secret
    token = jwe.encrypt(secret.encode("utf-8"), _encryption_key_bytes(settings), algorithm="dir", encryption="A256GCM")
    token_text = token.decode("utf-8") if isinstance(token, bytes) else str(token)
    return f"{_ENC_PREFIX}{token_text}"


def decrypt_webhook_secret(secret: str | None, settings: Settings) -> str | None:
    # Decrypt stored webhook secret if it was encrypted by this service.
    if not secret:
        return None
    if not secret.startswith(_ENC_PREFIX):
        return secret
    token = secret[len(_ENC_PREFIX) :]
    try:
        plaintext = jwe.decrypt(token, _encryption_key_bytes(settings))
    except Exception:
        return None
    if isinstance(plaintext, bytes):
        return plaintext.decode("utf-8")
    if isinstance(plaintext, str):
        return plaintext
    return base64.b64decode(plaintext).decode("utf-8")
