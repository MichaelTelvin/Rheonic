from typing import Protocol


class EmailTransport(Protocol):
    def send(self, *, to: str, subject: str, html: str, text: str | None = None) -> None:
        ...
