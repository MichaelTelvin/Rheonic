from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

from llmtokenburnguard import LLMTBGBlockedError, create_client
from llmtokenburnguard.providers.openai_adapter import instrument_openai

BACKEND_BASE_URL = os.getenv("LLMTBG_E2E_BACKEND_URL", "http://backend_test:8000")
PROVIDER_STUB_URL = os.getenv("LLMTBG_E2E_PROVIDER_URL", "http://provider_stub_test:8099")


@dataclass
class AuthContext:
    token: str
    project_id: str
    ingest_key: str


def _api(path: str, *, method: str = "GET", json: dict | None = None, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = httpx.request(method, f"{BACKEND_BASE_URL}{path}", json=json, headers=headers, timeout=5.0)
    response.raise_for_status()
    return response.json()


def _seed() -> AuthContext:
    nonce = int(time.time() * 1000)
    email = f"python-e2e-{nonce}@example.com"
    password = "password123"

    _api("/api/v1/auth/register", method="POST", json={"email": email, "password": password})
    login = _api("/api/v1/auth/login", method="POST", json={"email": email, "password": password})
    token = str(login["access_token"])

    project = _api(
        "/api/v1/projects",
        method="POST",
        token=token,
        json={"name": f"Python E2E {nonce}"},
    )
    project_id = str(project["id"])

    _api(
        f"/api/v1/projects/{project_id}/protect",
        method="PUT",
        token=token,
        json={
            "protect_enabled": True,
            "protect_fail_mode": "open",
            "protect_max_req_per_min": 10000,
            "protect_max_tok_per_min": 50000,
            "protect_decision_timeout_ms": 100,
        },
    )

    key_payload = _api(
        f"/api/v1/projects/{project_id}/keys",
        method="POST",
        token=token,
        json={"name": "python-e2e"},
    )

    return AuthContext(token=token, project_id=project_id, ingest_key=str(key_payload["key"]))


def _provider_reset() -> None:
    httpx.post(f"{PROVIDER_STUB_URL}/reset", timeout=3.0)


def _provider_count() -> int:
    response = httpx.get(f"{PROVIDER_STUB_URL}/count", timeout=3.0)
    response.raise_for_status()
    return int(response.json().get("count") or 0)


def run() -> None:
    auth = _seed()
    _provider_reset()

    client = create_client(ingest_key=auth.ingest_key, base_url=BACKEND_BASE_URL, flush_interval_s=60.0)

    class Completions:
        @staticmethod
        def create(**kwargs):
            httpx.post(f"{PROVIDER_STUB_URL}/call", json=kwargs, timeout=3.0).raise_for_status()
            return type("Response", (), {"model": kwargs.get("model", "gpt-4o-mini"), "usage": type("Usage", (), {"total_tokens": 10})()})()

    class Chat:
        completions = Completions()

    class OpenAIStub:
        chat = Chat()

    openai = OpenAIStub()
    instrument_openai(openai, client=client, feature="python-e2e")

    openai.chat.completions.create(model="gpt-4o-mini", max_tokens=128, input_tokens=10)
    assert _provider_count() == 1

    ingest_response = httpx.post(
        f"{BACKEND_BASE_URL}/api/v1/events",
        json={
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "provider": "openai",
            "model": "gpt-4o-mini",
            "environment": "dev",
            "response": {"total_tokens": 49000},
        },
        headers={"X-Project-Ingest-Key": auth.ingest_key, "Content-Type": "application/json"},
        timeout=5.0,
    )
    assert ingest_response.status_code == 202

    blocked = False
    try:
        openai.chat.completions.create(model="gpt-4o-mini", max_tokens=2000, input_tokens=0)
    except LLMTBGBlockedError:
        blocked = True
    assert blocked is True
    assert _provider_count() == 1

    protect_metrics = _api(f"/api/v1/metrics/protect?project_id={auth.project_id}", token=auth.token)
    assert int(protect_metrics.get("block_60m") or 0) >= 1

    client.close()
    print("python protect e2e PASSED")


if __name__ == "__main__":
    run()
