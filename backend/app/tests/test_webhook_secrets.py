from __future__ import annotations

import pytest

from app.config import Settings
from app.security.webhook_secrets import decrypt_webhook_secret, encrypt_webhook_secret


def test_webhook_secret_roundtrip_uses_authenticated_encryption() -> None:
    settings = Settings(jwt_secret="x" * 48, webhook_secret_encryption_key="k" * 32)
    encrypted = encrypt_webhook_secret("top-secret", settings)

    assert encrypted.startswith("enc:v1:")
    assert encrypted != "top-secret"
    assert decrypt_webhook_secret(encrypted, settings) == "top-secret"


def test_webhook_secret_decrypt_returns_none_with_wrong_key() -> None:
    source = Settings(jwt_secret="x" * 48, webhook_secret_encryption_key="k" * 32)
    wrong = Settings(jwt_secret="y" * 48, webhook_secret_encryption_key="z" * 32)
    encrypted = encrypt_webhook_secret("top-secret", source)

    assert decrypt_webhook_secret(encrypted, wrong) is None


def test_webhook_secret_encrypt_requires_key_material() -> None:
    settings = Settings(jwt_secret="", webhook_secret_encryption_key="")

    with pytest.raises(ValueError, match="WEBHOOK_SECRET_ENCRYPTION_KEY or JWT_SECRET"):
        encrypt_webhook_secret("top-secret", settings)
