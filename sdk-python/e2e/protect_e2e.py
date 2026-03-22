from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx
from rheonic import RHEONICBlockedError, create_client
from rheonic.providers.anthropic_adapter import instrument_anthropic
from rheonic.providers.google_adapter import instrument_google
from rheonic.providers.openai_adapter import instrument_openai

BACKEND_BASE_URL = os.getenv("RHEONIC_E2E_BACKEND_URL", "http://backend_test:8000")
PROVIDER_STUB_URL = os.getenv("RHEONIC_E2E_PROVIDER_URL", "http://provider_stub_test:8099")


@dataclass
class AuthContext:
    session: httpx.Client
    project_id: str
    ingest_key: str


def _api(client: httpx.Client, path: str, *, method: str = "GET", json: dict | None = None, retry: bool = True) -> dict:
    response = client.request(method, path, json=json)
    if response.status_code == 401 and retry and not path.startswith("/api/v1/auth/"):
        refresh_response = client.post("/api/v1/auth/refresh")
        if refresh_response.is_success:
            return _api(client, path, method=method, json=json, retry=False)
    response.raise_for_status()
    return response.json()


def _seed() -> AuthContext:
    nonce = int(time.time() * 1000)
    email = f"python-e2e-{nonce}@example.com"
    password = "Password123!"
    session = httpx.Client(base_url=BACKEND_BASE_URL, timeout=5.0)

    _api(session, "/api/v1/auth/register", method="POST", json={"email": email, "password": password})
    _api(session, "/api/v1/auth/login", method="POST", json={"email": email, "password": password}, retry=False)

    project = _api(
        session,
        "/api/v1/projects",
        method="POST",
        json={"name": f"Python E2E {nonce}"},
    )
    project_id = str(project["id"])

    _api(
        session,
        f"/api/v1/projects/{project_id}/protect",
        method="PUT",
        json={
            "protect_enabled": True,
            "protect_fail_mode": "open",
            "apply_clamp": False,
            "protect_max_req_per_min": 10000,
            "protect_max_tok_per_min": 50000,
        },
    )

    key_payload = _api(
        session,
        f"/api/v1/projects/{project_id}/keys",
        method="POST",
        json={"name": "python-e2e"},
    )

    return AuthContext(session=session, project_id=project_id, ingest_key=str(key_payload["key"]))


def _provider_reset() -> None:
    response = httpx.post(f"{PROVIDER_STUB_URL}/reset", timeout=3.0)
    response.raise_for_status()


def _provider_count() -> int:
    response = httpx.get(f"{PROVIDER_STUB_URL}/count", timeout=3.0)
    response.raise_for_status()
    return int(response.json().get("count") or 0)


def _provider_last_call() -> dict:
    response = httpx.get(f"{PROVIDER_STUB_URL}/last", timeout=3.0)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _make_openai_stub():
    class Completions:
        @staticmethod
        def create(**kwargs):
            httpx.post(f"{PROVIDER_STUB_URL}/call", json=kwargs, timeout=3.0).raise_for_status()
            return type(
                "Response",
                (),
                {"model": kwargs.get("model", "gpt-4o-mini"), "usage": type("Usage", (), {"total_tokens": 10})()},
            )()

    class Chat:
        completions = Completions()

    class OpenAIStub:
        chat = Chat()

    return OpenAIStub()


def run() -> None:
    auth = _seed()
    preflight_response = httpx.post(
        f"{BACKEND_BASE_URL}/api/v1/protect/decision",
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "environment": "dev",
            "feature": "python-e2e",
            "input_tokens_estimate": 12,
            "max_output_tokens": 32,
        },
        headers={"X-Project-Ingest-Key": auth.ingest_key, "Content-Type": "application/json"},
        timeout=5.0,
    )
    assert preflight_response.status_code == 200
    assert int(preflight_response.headers.get("X-Protect-Decision-Latency-Ms", "0")) >= 0

    _provider_reset()
    initial_provider_calls = _provider_count()

    client = create_client(
        ingest_key=auth.ingest_key,
        base_url=BACKEND_BASE_URL,
        flush_interval_s=60.0,
    )

    class AnthropicMessages:
        @staticmethod
        def create(**kwargs):
            httpx.post(f"{PROVIDER_STUB_URL}/call", json=kwargs, timeout=3.0).raise_for_status()

            class _Usage:
                input_tokens = 8
                output_tokens = 6
                total_tokens = 14

            class _Response:
                model = kwargs.get("model", "claude-3-5-sonnet-20240620")
                usage = _Usage()

            return _Response()

    class AnthropicStub:
        messages = AnthropicMessages()

    class GoogleUsage:
        prompt_token_count = 7
        candidates_token_count = 5
        total_token_count = 12

    class GoogleResponse:
        usage_metadata = GoogleUsage()

    class GoogleModelStub:
        model_name = "gemini-1.5-pro"

        @staticmethod
        def generate_content(prompt):
            httpx.post(f"{PROVIDER_STUB_URL}/call", json={"prompt": prompt}, timeout=3.0).raise_for_status()
            return GoogleResponse()

    openai = _make_openai_stub()
    anthropic = AnthropicStub()
    google_model = GoogleModelStub()
    instrument_openai(openai, client=client, feature="python-e2e")
    instrument_anthropic(anthropic, client=client, feature="python-e2e")
    instrument_google(google_model, client=client, feature="python-e2e")

    openai.chat.completions.create(model="gpt-4o-mini", max_tokens=128, input_tokens=10)
    anthropic.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=128,
        messages=[{"role": "user", "content": "anthropic e2e smoke"}],
    )
    google_model.generate_content("google e2e smoke")
    assert _provider_count() - initial_provider_calls == 3

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
        openai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=2000,
            messages=[{"role": "user", "content": "Predictive warning near cap check for python e2e clamp off."}],
        )
    except RHEONICBlockedError:
        blocked = True
    assert blocked is False
    assert _provider_count() - initial_provider_calls == 4
    assert int((_provider_last_call().get("payload") or {}).get("max_tokens") or 0) == 2000

    _api(
        auth.session,
        f"/api/v1/projects/{auth.project_id}/protect",
        method="PUT",
        json={
            "protect_enabled": True,
            "protect_fail_mode": "open",
            "apply_clamp": True,
            "protect_max_req_per_min": 10000,
            "protect_max_tok_per_min": 50000,
        },
    )

    blocked = False
    try:
        openai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=2000,
            messages=[{"role": "user", "content": "Predictive warning near cap check for python e2e clamp on."}],
        )
    except RHEONICBlockedError:
        blocked = True
    assert blocked is False
    assert _provider_count() - initial_provider_calls == 5
    clamped_max_tokens = int((_provider_last_call().get("payload") or {}).get("max_tokens") or 0)
    assert 0 < clamped_max_tokens < 2000

    protect_metrics = _api(auth.session, f"/api/v1/metrics/protect?project_id={auth.project_id}")
    assert int(protect_metrics.get("warned_60m") or 0) >= 2
    open_incidents = _api(
        auth.session,
        f"/api/v1/incidents?project_id={auth.project_id}&status=open&provider=openai",
    )
    assert isinstance(open_incidents, list)
    assert any(str(row.get("type")) == "near_cap" for row in open_incidents)

    metrics_before_cooldown = _api(auth.session, f"/api/v1/metrics/protect?project_id={auth.project_id}")
    blocked_before_cooldown = int(metrics_before_cooldown.get("blocked_60m") or 0)

    _api(
        auth.session,
        f"/api/v1/projects/{auth.project_id}/protect",
        method="PUT",
        json={
            "protect_enabled": True,
            "protect_fail_mode": "open",
            "apply_clamp": False,
            "protect_max_req_per_min": 1,
            "protect_max_tok_per_min": 50000,
        },
    )

    first_block_reason = ""
    try:
        openai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=128,
            messages=[{"role": "user", "content": "Cooldown backend block check."}],
        )
    except RHEONICBlockedError as error:
        first_block_reason = error.reason
    assert first_block_reason == "req_cap_breach"
    assert _provider_count() - initial_provider_calls == 5

    metrics_after_initial_block = _api(auth.session, f"/api/v1/metrics/protect?project_id={auth.project_id}")
    assert int(metrics_after_initial_block.get("blocked_60m") or 0) == blocked_before_cooldown + 1
    assert str((metrics_after_initial_block.get("last") or {}).get("reason") or "") == "req_cap_breach"
    assert str((metrics_after_initial_block.get("last") or {}).get("source") or "") == "live"

    local_cooldown_reason = ""
    try:
        openai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=128,
            messages=[{"role": "user", "content": "Cooldown local cached block check."}],
        )
    except RHEONICBlockedError as error:
        local_cooldown_reason = error.reason
    assert local_cooldown_reason == "cooldown_active"
    assert _provider_count() - initial_provider_calls == 5

    metrics_after_local_cooldown = _api(auth.session, f"/api/v1/metrics/protect?project_id={auth.project_id}")
    assert int(metrics_after_local_cooldown.get("blocked_60m") or 0) == blocked_before_cooldown + 1
    assert str((metrics_after_local_cooldown.get("last") or {}).get("reason") or "") == "req_cap_breach"

    cooldown_client = create_client(
        ingest_key=auth.ingest_key,
        base_url=BACKEND_BASE_URL,
        flush_interval_s=60.0,
    )
    cooldown_openai = _make_openai_stub()
    instrument_openai(cooldown_openai, client=cooldown_client, feature="python-e2e-cooldown")

    backend_cooldown_reason = ""
    try:
        cooldown_openai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=128,
            messages=[{"role": "user", "content": "Cooldown backend live decision check."}],
        )
    except RHEONICBlockedError as error:
        backend_cooldown_reason = error.reason
    assert backend_cooldown_reason == "cooldown_active"
    assert _provider_count() - initial_provider_calls == 5

    metrics_after_backend_cooldown = _api(auth.session, f"/api/v1/metrics/protect?project_id={auth.project_id}")
    assert int(metrics_after_backend_cooldown.get("blocked_60m") or 0) == blocked_before_cooldown + 2
    assert str((metrics_after_backend_cooldown.get("last") or {}).get("reason") or "") == "cooldown_active"
    assert str((metrics_after_backend_cooldown.get("last") or {}).get("source") or "") == "live"

    cooldown_client.close()
    client.close()
    auth.session.close()
    print("python protect e2e PASSED")


if __name__ == "__main__":
    run()
