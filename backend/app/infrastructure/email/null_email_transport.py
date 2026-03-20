from __future__ import annotations

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
        raise EmailProviderNotConfiguredError("email provider not configured")
