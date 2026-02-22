# Webhook URL validation helpers.
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from fastapi import HTTPException

from app.config import Settings


def normalize_webhook_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def ensure_webhook_url_is_safe(url: str, settings: Settings) -> None:
    # Reject unsafe webhook targets that can hit local/private network resources.
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=422, detail="Webhook URL must include a hostname")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Webhook URL must not include credentials")

    if settings.webhook_allow_private_hosts:
        return

    lowered_host = host.lower()
    if lowered_host in {"localhost", "ip6-localhost"} or lowered_host.endswith(".local"):
        raise HTTPException(status_code=422, detail="Webhook URL host is not allowed")

    try:
        address = ipaddress.ip_address(lowered_host)
    except ValueError:
        return

    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise HTTPException(status_code=422, detail="Webhook URL host is not allowed")
