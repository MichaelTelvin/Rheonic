from __future__ import annotations

import httpx

from app.logger import get_logger

logger = get_logger(__name__)


class ResendEmailTransportError(RuntimeError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ResendEmailTransport:
    def __init__(self, *, api_key: str, base_url: str = "https://api.resend.com") -> None:
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        if not self._api_key:
            raise ResendEmailTransportError(code="email_provider_not_configured", message="Resend API key is missing")

    def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str | None = None,
        from_email: str,
        reply_to: str | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "from": from_email,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if text:
            payload["text"] = text
        if reply_to:
            payload["reply_to"] = [reply_to]

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(f"{self._base_url}/emails", json=payload, headers=headers)
                response.raise_for_status()
                response_body = response.json()
        except httpx.HTTPStatusError as exc:
            message = _provider_error_message(exc.response)
            raise ResendEmailTransportError(code="email_provider_http_error", message=message) from exc
        except httpx.HTTPError as exc:
            raise ResendEmailTransportError(code="email_provider_request_error", message=str(exc)) from exc
        except ValueError as exc:
            raise ResendEmailTransportError(code="email_provider_response_error", message=str(exc)) from exc

        logger.info(
            "Resend email delivered",
            extra={
                "provider": "resend",
                "provider_message_id": response_body.get("id"),
            },
        )


def _provider_error_message(response: httpx.Response | None) -> str:
    if response is None:
        return "Resend request failed"
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        detail = body.get("message") or body.get("name") or body.get("error")
        if isinstance(detail, str) and detail.strip():
            return f"HTTP {response.status_code}: {detail.strip()}"
    text = (response.text or "").strip()
    if text:
        return f"HTTP {response.status_code}: {text[:240]}"
    return f"HTTP {response.status_code}"
