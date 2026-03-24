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

    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings()


def test_settings_prod_rejects_localhost_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_required_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")

    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings()


def test_settings_prod_valid_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_required_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com,https://ops.example.com")
    monkeypatch.setenv("PUBLIC_APP_BASE_URL", "https://beta.example.com")

    settings = Settings()
    assert settings.is_production_like
    assert settings.cors_origin_list == ["https://app.example.com", "https://ops.example.com"]
    assert settings.resolved_public_app_base_url == "https://beta.example.com"


def test_settings_prod_cookie_names_use_valid_secure_prefixes(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_required_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("PUBLIC_APP_BASE_URL", "https://staging.example.com")

    settings = Settings()
    assert settings.auth_access_cookie_name == "__Host-rheonic_access"
    assert settings.auth_refresh_cookie_name == "__Secure-rheonic_refresh"


def test_settings_prod_requires_https_public_app_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_required_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("PUBLIC_APP_BASE_URL", "http://localhost:5173")

    with pytest.raises(ValueError, match="PUBLIC_APP_BASE_URL"):
        Settings()


def test_settings_email_delivery_requires_sender_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_required_env(monkeypatch)
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.delenv("EMAIL_FROM_ALERTS", raising=False)
    monkeypatch.setenv("EMAIL_FROM_SYSTEM", "Rheonic System <system@mail.rheonic.dev>")
    monkeypatch.setenv("EMAIL_REPLY_TO", "contact@rheonic.dev")

    with pytest.raises(ValueError, match="EMAIL_FROM_ALERTS"):
        Settings()


def test_settings_email_delivery_requires_reply_to(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_required_env(monkeypatch)
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("EMAIL_FROM_ALERTS", "Rheonic Alerts <alerts@mail.rheonic.dev>")
    monkeypatch.setenv("EMAIL_FROM_SYSTEM", "Rheonic System <system@mail.rheonic.dev>")
    monkeypatch.delenv("EMAIL_REPLY_TO", raising=False)

    with pytest.raises(ValueError, match="EMAIL_REPLY_TO"):
        Settings()


def test_settings_email_delivery_allows_resend_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_required_env(monkeypatch)
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("EMAIL_FROM_ALERTS", "Rheonic Alerts <alerts@mail.rheonic.dev>")
    monkeypatch.setenv("EMAIL_FROM_SYSTEM", "Rheonic System <system@mail.rheonic.dev>")
    monkeypatch.setenv("EMAIL_REPLY_TO", "contact@rheonic.dev")

    settings = Settings()
    assert settings.resolved_email_provider == "resend"
    assert settings.resolved_email_provider_enabled is True
