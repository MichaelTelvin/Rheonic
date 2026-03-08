# Webhook secret encryption helpers.
from __future__ import annotations

import base64
from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings, app_config
from app.logger import get_logger

logger = get_logger(__name__)


def _encryption_key_bytes(settings: Settings) -> bytes:
    digest = bytes.fromhex(settings.webhook_secret_encryption_key_digest)
    return base64.urlsafe_b64encode(digest)


def encrypt_webhook_secret(secret: str, settings: Settings) -> str:
    # Encrypt webhook secret before persisting it.
    if not secret:
        return secret
    token_text = Fernet(_encryption_key_bytes(settings)).encrypt(secret.encode("utf-8")).decode("utf-8")
    return f"{app_config.webhook_secret_prefix}{token_text}"


def decrypt_webhook_secret(secret: str | None, settings: Settings) -> str | None:
    # Decrypt stored webhook secret if it was encrypted by this service.
    if not secret:
        return None
    if not secret.startswith(app_config.webhook_secret_prefix):
        return secret
    token = secret[len(app_config.webhook_secret_prefix) :]
    try:
        plaintext = Fernet(_encryption_key_bytes(settings)).decrypt(token.encode("utf-8"))
        return plaintext.decode("utf-8")
    except InvalidToken:
        logger.warning("Stored webhook secret could not be decrypted with the configured encryption key")
        return None
    except Exception:
        logger.exception("Webhook secret decryption failed unexpectedly")
        return None
