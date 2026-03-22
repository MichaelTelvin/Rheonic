from typing import Protocol


class EmailTransport(Protocol):
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
    ) -> None: ...
