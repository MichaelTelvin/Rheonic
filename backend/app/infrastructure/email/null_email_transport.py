from __future__ import annotations

from app.logger import get_logger

logger = get_logger(__name__)


class EmailProviderNotConfiguredError(RuntimeError):
    pass


class NullEmailTransport:
    def send(self, *, to: str, subject: str, html: str, text: str | None = None) -> None:
        _ = html, text
        logger.info("Null email transport invoked", extra={"to": to, "subject": subject})
        raise EmailProviderNotConfiguredError("email provider not configured")
