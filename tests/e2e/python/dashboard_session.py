from __future__ import annotations

from typing import Any

import httpx


class DashboardSession:
    def __init__(self, base_url: str, *, timeout_s: float = 5.0) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s)

    def login(self, email: str, password: str) -> dict[str, Any]:
        payload = self.request("/api/v1/auth/login", method="POST", json={"email": email, "password": password}, retry=False)
        return payload if isinstance(payload, dict) else {}

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        json: dict[str, Any] | None = None,
        retry: bool = True,
        params: dict[str, Any] | None = None,
    ) -> Any:
        response = self._client.request(method, path, json=json, params=params)
        if response.status_code == 401 and retry and not path.startswith("/api/v1/auth/"):
            if self.refresh():
                return self.request(path, method=method, json=json, retry=False, params=params)
        response.raise_for_status()
        return response.json()

    def refresh(self) -> bool:
        try:
            self.request("/api/v1/auth/refresh", method="POST", retry=False)
            return True
        except httpx.HTTPError:
            return False

    def close(self) -> None:
        self._client.close()
