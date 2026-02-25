from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from llmtokenburnguard.client import Client
from llmtokenburnguard.protect_engine import LLMTBGBlockedError
from llmtokenburnguard.providers.anthropic_adapter import instrument_anthropic
from llmtokenburnguard.providers.google_adapter import instrument_google
from llmtokenburnguard.providers.openai_adapter import instrument_openai


def _load_llmtbg_env_from_dotenv() -> None:
    dotenv_path = Path(__file__).resolve().parents[1] / ".env"
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key.startswith("LLMTBG_"):
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


_load_llmtbg_env_from_dotenv()

BACKEND_BASE_URL = os.getenv("LLMTBG_BACKEND_URL", "http://localhost:8000")
PROVIDER_STUB_URL = os.getenv("LLMTBG_PROVIDER_URL", "http://localhost:8099")


class LoggingHttpClient:
    def __init__(self, timeout_s: float) -> None:
        self._client = httpx.Client(timeout=timeout_s)
        self.last_decision_request: dict[str, Any] | None = None
        self.last_decision_response: dict[str, Any] | None = None

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str], timeout: float | None = None) -> httpx.Response:
        if url.endswith("/api/v1/protect/decision"):
            self.last_decision_request = dict(json)
            print("=== PROTECT DECISION REQUEST ===")
            print(_json_dumps(self.last_decision_request))
            response = self._client.post(url, json=json, headers=headers, timeout=timeout)
            payload: dict[str, Any]
            try:
                parsed = response.json()
                payload = parsed if isinstance(parsed, dict) else {"raw": parsed}
            except Exception:
                payload = {"status_code": response.status_code, "body": response.text}
            self.last_decision_response = payload
            print("=== PROTECT DECISION RESPONSE ===")
            print(_json_dumps(payload))
            return response
        return self._client.post(url, json=json, headers=headers, timeout=timeout)

    def close(self) -> None:
        self._client.close()


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _provider_reset() -> None:
    try:
        httpx.post(f"{PROVIDER_STUB_URL}/reset", timeout=3.0).raise_for_status()
    except Exception:
        pass


def _provider_count() -> int | None:
    try:
        response = httpx.get(f"{PROVIDER_STUB_URL}/count", timeout=3.0)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            value = payload.get("count")
            if isinstance(value, int):
                return value
        return None
    except Exception:
        return None


def _make_openai_stub() -> Any:
    class Completions:
        @staticmethod
        def create(**kwargs: Any) -> Any:
            httpx.post(f"{PROVIDER_STUB_URL}/call", json=kwargs, timeout=3.0).raise_for_status()
            usage = type("Usage", (), {"total_tokens": 10})()
            return type("Response", (), {"model": kwargs.get("model"), "usage": usage})()

    class Chat:
        completions = Completions()

    class OpenAIStub:
        chat = Chat()

    return OpenAIStub()


def _make_anthropic_stub() -> Any:
    class Messages:
        @staticmethod
        def create(**kwargs: Any) -> Any:
            httpx.post(f"{PROVIDER_STUB_URL}/call", json=kwargs, timeout=3.0).raise_for_status()
            usage = type("Usage", (), {"input_tokens": 6, "output_tokens": 4})()
            return type("Response", (), {"model": kwargs.get("model"), "usage": usage})()

    class AnthropicStub:
        messages = Messages()

    return AnthropicStub()


def _make_google_stub() -> Any:
    class UsageMetadata:
        total_token_count = 10

    class GoogleResponse:
        usage_metadata = UsageMetadata()

    class GoogleModelStub:
        model_name = ""

        @staticmethod
        def generate_content(prompt: str) -> Any:
            httpx.post(f"{PROVIDER_STUB_URL}/call", json={"prompt": prompt}, timeout=3.0).raise_for_status()
            return GoogleResponse()

    return GoogleModelStub()


def _print_provider_stub_help() -> None:
    print(f"ERROR: provider stub is unreachable at {PROVIDER_STUB_URL}")
    print("Start it with `python3 tests/e2e/provider_stub.py` or set LLMTBG_PROVIDER_URL to a reachable endpoint.")


def _send_ingest_event(ingest_key: str, provider: str, model: str, total_tokens: int, feature: str) -> None:
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": provider,
        "model": model,
        "environment": os.getenv("LLMTBG_ENV", "dev"),
        "request": {"endpoint": "/chat/completions", "feature": feature, "input_tokens": 1},
        "response": {"output_tokens": 1, "total_tokens": total_tokens, "latency_ms": 120, "http_status": 200},
    }
    response = httpx.post(
        f"{BACKEND_BASE_URL}/api/v1/events",
        json=payload,
        headers={"X-Project-Ingest-Key": ingest_key},
        timeout=5.0,
    )
    response.raise_for_status()


def _list_open_incidents(project_id: str, provider: str, auth_token: str) -> list[dict[str, Any]]:
    params = {"project_id": project_id, "status": "open"}
    if provider:
        params["provider"] = provider
    response = httpx.get(
        f"{BACKEND_BASE_URL}/api/v1/incidents",
        params=params,
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=5.0,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def _resolve_incident(incident_id: str, auth_token: str) -> None:
    response = httpx.post(
        f"{BACKEND_BASE_URL}/api/v1/incidents/{incident_id}/resolve",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={},
        timeout=5.0,
    )
    response.raise_for_status()


def _print_webhook_status(project_id: str, auth_token: str) -> None:
    response = httpx.get(
        f"{BACKEND_BASE_URL}/api/v1/projects/{project_id}/webhook",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=5.0,
    )
    if response.status_code != 200:
        print(f"[OBSERVE] webhook status unavailable (status={response.status_code})")
        return
    payload = response.json() if isinstance(response.json(), dict) else {}
    print(
        "[OBSERVE] webhook last_delivery="
        f"{payload.get('webhook_last_delivery_status', 'none')} "
        f"at {payload.get('webhook_last_delivery_at', 'n/a')}"
    )


def _run_protect_harness(
    provider: str,
    model: str,
    scenario: str,
    openai: Any,
    anthropic: Any,
    google: Any,
    client: Client,
) -> None:
    max_tokens = int(os.getenv("LLMTBG_MAX_TOKENS", "2000" if scenario == "block" else "128"))
    before = _provider_count()

    print("\n[STEP] Protect decision preflight")
    print(f"[EXPECT] scenario={scenario} should produce allow/warn/block before provider call")

    blocked = False
    try:
        if provider == "anthropic":
            anthropic.messages.create(
                model=model,
                messages=[{"role": "user", "content": f"Protect harness request. scenario={scenario}"}],
                max_tokens=max_tokens,
            )
        elif provider == "google":
            google.generate_content(f"Protect harness request. scenario={scenario}")
        else:
            openai.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": f"Protect harness request. scenario={scenario}"}],
                max_tokens=max_tokens,
            )
    except LLMTBGBlockedError:
        blocked = True

    client.flush()
    after = _provider_count()
    if blocked:
        print(f"[OBSERVE] blocked by protect preflight for scenario={scenario}")
    else:
        print(f"[OBSERVE] provider call executed for scenario={scenario}")
    if before is not None and after is not None:
        print({"provider_calls_delta": after - before, "before": before, "after": after})


def _run_webhooks_harness(
    ingest_key: str,
    provider: str,
    model: str,
    auth_token: str,
    project_id: str,
    pause_ms: int,
) -> None:
    print("\n[STEP] Warm-up behavior")
    print("[EXPECT] tiny early traffic should not create ratio-based incident")
    _send_ingest_event(ingest_key, provider, model, 42, "harness-warmup-1")
    time.sleep(pause_ms / 1000)
    _send_ingest_event(ingest_key, provider, model, 42, "harness-warmup-2")

    print("\n[STEP] High-open + webhook")
    print("[EXPECT] high incident opens and webhook incident.high is dispatched")
    for i in range(8):
        _send_ingest_event(ingest_key, provider, model, 100, f"harness-baseline-{i + 1}")
        time.sleep(pause_ms / 1000)
    _send_ingest_event(ingest_key, provider, model, 60000, "harness-high-open")

    print("\n[STEP] Escalation + webhook")
    print("[EXPECT] repeated hits escalate to high and dispatch incident.high (source=escalation)")
    _send_ingest_event(ingest_key, provider, model, 60000, "harness-escalation-1")
    time.sleep(pause_ms / 1000)
    _send_ingest_event(ingest_key, provider, model, 60000, "harness-escalation-2")

    if auth_token and project_id:
        incidents = _list_open_incidents(project_id, provider, auth_token)
        print(f"[OBSERVE] open incidents in scope={len(incidents)}")
        if incidents:
            print("\n[STEP] Manual resolve + webhook")
            print("[EXPECT] incident.resolved webhook dispatched with resolved_by=manual")
            _resolve_incident(str(incidents[0].get("id")), auth_token)
        print("\n[STEP] Auto-resolve + webhook")
        print("[EXPECT] after inactivity cooldown, auto-resolve emits incident.resolved with resolved_by=auto")
        print("[OBSERVE] wait incident_auto_close_seconds, then check incidents/webhook status")
        _print_webhook_status(project_id, auth_token)
    else:
        print("[OBSERVE] set LLMTBG_AUTH_TOKEN + LLMTBG_PROJECT_ID to verify resolve/webhook status via API")


def main() -> None:
    ingest_key = os.getenv("LLMTBG_INGEST_KEY")
    if not ingest_key:
        print("LLMTBG_INGEST_KEY is required.")
        sys.exit(1)

    scenario = (os.getenv("LLMTBG_SCENARIO", "allow") or "allow").lower()
    provider = (os.getenv("LLMTBG_PROVIDER", "") or "").strip().lower()
    if not provider:
        print("LLMTBG_PROVIDER is required (openai | anthropic | google).")
        sys.exit(1)
    if provider not in {"openai", "anthropic", "google"}:
        print(f"LLMTBG_PROVIDER is unsupported: {provider}")
        sys.exit(1)

    model = (os.getenv("LLMTBG_MODEL", "") or "").strip()
    if not model:
        print(f"LLMTBG_MODEL is required for provider {provider}.")
        sys.exit(1)

    harness_case = (os.getenv("LLMTBG_HARNESS_CASE", "protect") or "protect").lower()
    pause_ms = int(os.getenv("LLMTBG_STEP_SLEEP_MS", "800"))
    auth_token = os.getenv("LLMTBG_AUTH_TOKEN", "")
    project_id = os.getenv("LLMTBG_PROJECT_ID", "")

    transport = LoggingHttpClient(timeout_s=5.0)
    client = Client(
        ingest_key=ingest_key,
        base_url=BACKEND_BASE_URL,
        protect_enabled=True,
        environment=os.getenv("LLMTBG_ENVIRONMENT", "dev"),
        flush_interval_s=60.0,
        http_client=transport,
    )

    openai = _make_openai_stub()
    anthropic = _make_anthropic_stub()
    google = _make_google_stub()
    google.model_name = model

    instrument_openai(openai, client=client, feature="manual-protect-demo", environment=os.getenv("LLMTBG_ENVIRONMENT", "dev"))
    instrument_anthropic(anthropic, client=client, feature="manual-protect-demo", environment=os.getenv("LLMTBG_ENVIRONMENT", "dev"))
    instrument_google(google, client=client, feature="manual-protect-demo", environment=os.getenv("LLMTBG_ENVIRONMENT", "dev"))

    _provider_reset()
    if _provider_count() is None:
        _print_provider_stub_help()
        client.close()
        transport.close()
        return

    print(f"[DEMO] provider={provider} model={model} harness={harness_case}")
    print("[DEMO] provider scoping active: counters/incidents/decisions are isolated by provider")

    try:
        if harness_case == "all":
            _run_protect_harness(provider, model, scenario, openai, anthropic, google, client)
            _run_webhooks_harness(ingest_key, provider, model, auth_token, project_id, pause_ms)
        elif harness_case == "protect":
            _run_protect_harness(provider, model, scenario, openai, anthropic, google, client)
        elif harness_case == "webhooks":
            _run_webhooks_harness(ingest_key, provider, model, auth_token, project_id, pause_ms)
        else:
            print(f"Unsupported LLMTBG_HARNESS_CASE: {harness_case}")
            sys.exit(1)
    except httpx.ConnectError:
        _print_provider_stub_help()
    finally:
        client.flush()
        print("[DEMO] sdk delivery stats:", client.stats())
        client.close()
        transport.close()


if __name__ == "__main__":
    main()
