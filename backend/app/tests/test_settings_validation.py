from __future__ import annotations

import pytest

from app.config import Settings


def _base_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_DB", "rheonic")
    monkeypatch.setenv("POSTGRES_USER", "rheonic")
    monkeypatch.setenv("POSTGRES_PASSWORD", "rheonic")
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("REDIS_HOST", "redis")
    monkeypatch.setenv("REDIS_PORT", "6379")


def test_settings_prod_requires_strong_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_required_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", "short")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("WEBHOOK_SECRET_ENCRYPTION_KEY", "k" * 32)

    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings()


def test_settings_prod_rejects_localhost_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_required_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("WEBHOOK_SECRET_ENCRYPTION_KEY", "k" * 32)

    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings()


def test_settings_prod_valid_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_required_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com,https://ops.example.com")
    monkeypatch.setenv("WEBHOOK_SECRET_ENCRYPTION_KEY", "k" * 32)

    settings = Settings()
    assert settings.is_production_like
    assert settings.cors_origin_list == ["https://app.example.com", "https://ops.example.com"]


def test_settings_prod_requires_strong_webhook_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_required_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("WEBHOOK_SECRET_ENCRYPTION_KEY", "short")

    with pytest.raises(ValueError, match="WEBHOOK_SECRET_ENCRYPTION_KEY"):
        Settings()


def test_settings_prod_cookie_names_use_valid_secure_prefixes(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_required_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("WEBHOOK_SECRET_ENCRYPTION_KEY", "k" * 32)

    settings = Settings()
    assert settings.auth_access_cookie_name == "__Host-rheonic_access"
    assert settings.auth_refresh_cookie_name == "__Secure-rheonic_refresh"
