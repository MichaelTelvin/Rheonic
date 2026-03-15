from __future__ import annotations

import httpx
import pytest

from app.infrastructure.email.resend_email_transport import ResendEmailTransport, ResendEmailTransportError


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, body: dict[str, object] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._body = body or {"id": "re_123"}
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://api.resend.com/emails")
            response = httpx.Response(self.status_code, request=request, json=self._body)
            raise httpx.HTTPStatusError("request failed", request=request, response=response)

    def json(self) -> dict[str, object]:
        return self._body


class _FakeClient:
    def __init__(self, sent: list[dict[str, object]], response: _FakeResponse) -> None:
        self.sent = sent
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb

    def post(self, url: str, json: dict[str, object], headers: dict[str, str]):
        self.sent.append({"url": url, "json": json, "headers": headers})
        return self.response


def test_resend_email_transport_formats_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.infrastructure.email.resend_email_transport.httpx.Client",
        lambda timeout: _FakeClient(sent, _FakeResponse()),
    )

    transport = ResendEmailTransport(api_key="re_test")
    transport.send(
        to="owner@example.com",
        subject="Protect alert",
        html="<p>hello</p>",
        text="hello",
        from_email="Rheonic Alerts <alerts@mail.rheonic.dev>",
        reply_to="contact@rheonic.dev",
    )

    assert len(sent) == 1
    payload = sent[0]["json"]
    assert sent[0]["url"] == "https://api.resend.com/emails"
    assert payload["from"] == "Rheonic Alerts <alerts@mail.rheonic.dev>"
    assert payload["to"] == ["owner@example.com"]
    assert payload["reply_to"] == ["contact@rheonic.dev"]
    assert payload["subject"] == "Protect alert"


def test_resend_email_transport_surfaces_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.infrastructure.email.resend_email_transport.httpx.Client",
        lambda timeout: _FakeClient([], _FakeResponse(status_code=422, body={"message": "invalid sender"})),
    )

    transport = ResendEmailTransport(api_key="re_test")
    with pytest.raises(ResendEmailTransportError, match="invalid sender") as exc_info:
        transport.send(
            to="owner@example.com",
            subject="Protect alert",
            html="<p>hello</p>",
            from_email="bad",
        )

    assert exc_info.value.code == "email_provider_http_error"
