from __future__ import annotations

from app.logger import get_logger

logger = get_logger(__name__)


class EmailProviderNotConfiguredError(RuntimeError):
    pass


class NullEmailTransport:
    def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str | None = None,
        from_email: str,
        reply_to: str | None = None,
        attachments: list[dict[str, str]] | None = None,
    ) -> None:
        _ = to, subject, html, text, from_email, reply_to, attachments
        logger.info("Null email transport invoked")
        raise EmailProviderNotConfiguredError("email provider not configured")
