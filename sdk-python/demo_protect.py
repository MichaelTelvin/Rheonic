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
_LAST_PROVIDER_CALL: dict[str, Any] | None = None


class LoggingHttpClient:
    def __init__(self, timeout_s: float) -> None:
        self._client = httpx.Client(timeout=timeout_s)
        self.last_decision_payload: dict[str, Any] | None = None

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str], timeout: float | None = None) -> httpx.Response:
        if url.endswith("/api/v1/protect/decision"):
            print("=== PROTECT DECISION REQUEST ===")
            print(json.dumps(json, indent=2, sort_keys=True))
        response = self._client.post(url, json=json, headers=headers, timeout=timeout)
        if url.endswith("/api/v1/protect/decision"):
            payload: dict[str, Any]
            try:
                parsed = response.json()
                payload = parsed if isinstance(parsed, dict) else {"raw": parsed}
            except Exception:
                payload = {"status_code": response.status_code, "body": response.text}
            self.last_decision_payload = payload
            print("=== PROTECT DECISION RESPONSE ===")
            print(json.dumps(payload, indent=2, sort_keys=True))
        return response

    def close(self) -> None:
        self._client.close()


def _provider_reset() -> None:
    httpx.post(f"{PROVIDER_STUB_URL}/reset", timeout=3.0).raise_for_status()


def _provider_count() -> int:
    response = httpx.get(f"{PROVIDER_STUB_URL}/count", timeout=3.0)
    response.raise_for_status()
    payload = response.json()
    return int(payload.get("count", 0)) if isinstance(payload, dict) else 0


def _provider_last_call() -> dict[str, Any] | None:
    return _LAST_PROVIDER_CALL.copy() if isinstance(_LAST_PROVIDER_CALL, dict) else None


def _record_provider_call(payload: dict[str, Any]) -> None:
    global _LAST_PROVIDER_CALL
    _LAST_PROVIDER_CALL = payload.copy()


def _extract_used_max_tokens(payload: dict[str, Any] | None) -> int | None:
    if not payload:
        return None
    raw = payload.get("max_tokens")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    return None


def _assert_line(label: str, passed: bool) -> None:
    print(f"[ASSERT] {label}" if passed else f"[ASSERT] {label} (FAILED)")


def _make_openai_stub() -> Any:
    class Completions:
        @staticmethod
        def create(**kwargs: Any) -> Any:
            _record_provider_call(kwargs)
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
            _record_provider_call(kwargs)
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
            payload = {"prompt": prompt}
            _record_provider_call(payload)
            httpx.post(f"{PROVIDER_STUB_URL}/call", json=payload, timeout=3.0).raise_for_status()
            return GoogleResponse()

    return GoogleModelStub()


def _send_ingest_event(
    ingest_key: str,
    provider: str,
    model: str,
    *,
    total_tokens: int,
    feature: str,
    environment: str,
    status: str = "ok",
    http_status: int = 200,
    error_type: str | None = None,
) -> None:
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": provider,
        "model": model,
        "environment": environment,
        "request": {"endpoint": "/chat/completions", "feature": feature, "input_tokens": 1},
        "response": {
            "output_tokens": 1,
            "total_tokens": total_tokens,
            "latency_ms": 120,
            "http_status": http_status,
            **({"error_type": error_type} if error_type else {}),
        },
        "status": status,
    }
    response = httpx.post(
        f"{BACKEND_BASE_URL}/api/v1/events",
        json=payload,
        headers={"X-Project-Ingest-Key": ingest_key},
        timeout=5.0,
    )
    response.raise_for_status()


def _list_open_incidents(project_id: str, provider: str, auth_token: str) -> list[dict[str, Any]]:
    if not auth_token or not project_id:
        return []
    params = {"project_id": project_id, "status": "open", "provider": provider}
    response = httpx.get(
        f"{BACKEND_BASE_URL}/api/v1/incidents",
        params=params,
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=5.0,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def _print_incidents(project_id: str, provider: str, auth_token: str) -> None:
    incidents = _list_open_incidents(project_id, provider, auth_token)
    counts: dict[str, int] = {}
    for incident in incidents:
        incident_type = str(incident.get("type", "unknown"))
        counts[incident_type] = counts.get(incident_type, 0) + 1
    compact = ", ".join(f"{k}={counts[k]}" for k in sorted(counts)) if counts else "none"
    print(f"[INCIDENTS] open={len(incidents)} types={compact}")


def _run_provider_call(provider: str, model: str, max_tokens: int, openai: Any, anthropic: Any, google: Any) -> bool:
    blocked = False
    try:
        if provider == "anthropic":
            anthropic.messages.create(
                model=model,
                messages=[{"role": "user", "content": "protect demo request"}],
                max_tokens=max_tokens,
            )
        elif provider == "google":
            google.generate_content("protect demo request")
        else:
            openai.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "protect demo request"}],
                max_tokens=max_tokens,
            )
    except LLMTBGBlockedError:
        blocked = True
    return blocked


def main() -> None:
    ingest_key = os.getenv("LLMTBG_INGEST_KEY")
    if not ingest_key:
        print("LLMTBG_INGEST_KEY is required")
        sys.exit(1)

    provider = (os.getenv("LLMTBG_PROVIDER", "") or "").strip().lower()
    if provider not in {"openai", "anthropic", "google"}:
        print("LLMTBG_PROVIDER is required (openai | anthropic | google)")
        sys.exit(1)

    model = (os.getenv("LLMTBG_MODEL", "") or "").strip()
    if not model:
        print(f"LLMTBG_MODEL is required for provider {provider}")
        sys.exit(1)

    scenario = (os.getenv("LLMTBG_SCENARIO") or "allow").strip().lower()
    env = (os.getenv("LLMTBG_ENVIRONMENT") or "").strip() or f"protect-{int(time.time())}"
    pause_ms = int(os.getenv("LLMTBG_STEP_SLEEP_MS", "200"))
    project_id = os.getenv("LLMTBG_PROJECT_ID", "")
    auth_token = os.getenv("LLMTBG_AUTH_TOKEN", "")

    transport = LoggingHttpClient(timeout_s=5.0)
    client = Client(
        ingest_key=ingest_key,
        base_url=BACKEND_BASE_URL,
        protect_enabled=True,
        environment=env,
        flush_interval_s=60.0,
        http_client=transport,
    )

    openai = _make_openai_stub()
    anthropic = _make_anthropic_stub()
    google = _make_google_stub()
    google.model_name = model

    instrument_openai(openai, client=client, feature="manual-protect-demo", environment=env)
    instrument_anthropic(anthropic, client=client, feature="manual-protect-demo", environment=env)
    instrument_google(google, client=client, feature="manual-protect-demo", environment=env)

    _provider_reset()
    before_calls = _provider_count()

    print(f"[DEMO] provider={provider} model={model} scenario={scenario}")
    print(f"[DEMO] environment={env}")

    max_tokens = int(os.getenv("LLMTBG_MAX_TOKENS", "128"))
    print(f"[DEMO] max_tokens(before call)={max_tokens}")

    if scenario == "near_cap":
        print("\n[STEP] Seed near-cap traffic then expect warn")
        seed_tokens = int(os.getenv("LLMTBG_NEAR_CAP_SEED_TOKENS", "1600"))
        _send_ingest_event(ingest_key, provider, model, total_tokens=seed_tokens, feature="near-cap-seed", environment=env)
        time.sleep(pause_ms / 1000)
    elif scenario == "cap_breach":
        print("\n[STEP] Seed cap breach then expect block")
        breach_tokens = int(os.getenv("LLMTBG_CAP_BREACH_TOKENS", "5000"))
        _send_ingest_event(ingest_key, provider, model, total_tokens=breach_tokens, feature="cap-breach-seed", environment=env)
        time.sleep(pause_ms / 1000)
    elif scenario == "req_cap_breach":
        print("\n[STEP] Seed req cap breach then expect block")
        count = int(os.getenv("LLMTBG_REQ_CAP_BREACH_COUNT", "6"))
        req_tokens = int(os.getenv("LLMTBG_CAP_BREACH_REQ_TOKENS", "1"))
        for i in range(count):
            _send_ingest_event(
                ingest_key,
                provider,
                model,
                total_tokens=req_tokens,
                feature=f"req-cap-breach-{i+1}",
                environment=env,
            )
            time.sleep(pause_ms / 1000)
    elif scenario == "retry_storm":
        print("\n[STEP] Seed retry storm then expect warn")
        count = int(os.getenv("LLMTBG_RETRY_STORM_COUNT", "6"))
        for i in range(count):
            _send_ingest_event(
                ingest_key,
                provider,
                model,
                total_tokens=50,
                feature=f"retry-{i+1}",
                environment=env,
                status="error",
                http_status=500,
                error_type="provider_5xx",
            )
            time.sleep(pause_ms / 1000)
    elif scenario == "loop_suspect":
        print("\n[STEP] Seed loop suspect then expect warn")
        count = int(os.getenv("LLMTBG_LOOP_COUNT", "7"))
        for _ in range(count):
            _send_ingest_event(ingest_key, provider, model, total_tokens=60, feature="loop-fixed-signature", environment=env)
            time.sleep(pause_ms / 1000)
    elif scenario == "token_explosion":
        print("\n[STEP] Seed token explosion then expect warn")
        huge = int(os.getenv("LLMTBG_TOKEN_EXPLOSION_TOKENS", "9000"))
        _send_ingest_event(ingest_key, provider, model, total_tokens=huge, feature="token-explosion-seed", environment=env)
        time.sleep(pause_ms / 1000)
    elif scenario == "cooldown":
        print("\n[STEP] Seed cap breach then verify cooldown blocks repeated call")
        breach_tokens = int(os.getenv("LLMTBG_CAP_BREACH_TOKENS", "5000"))
        _send_ingest_event(ingest_key, provider, model, total_tokens=breach_tokens, feature="cooldown-breach-seed", environment=env)
        time.sleep(pause_ms / 1000)

    if scenario == "cooldown":
        first_blocked = _run_provider_call(provider, model, max_tokens, openai, anthropic, google)
        second_blocked = _run_provider_call(provider, model, max_tokens, openai, anthropic, google)
        blocked = first_blocked and second_blocked
    else:
        blocked = _run_provider_call(provider, model, max_tokens, openai, anthropic, google)
    client.flush()
    after_calls = _provider_count()
    provider_calls_delta = after_calls - before_calls
    decision_payload = transport.last_decision_payload if isinstance(transport.last_decision_payload, dict) else {}
    decision_reason = str(decision_payload.get("reason", ""))
    decision_value = str(decision_payload.get("decision", "")).lower()
    clamp = decision_payload.get("clamp")
    clamp_payload = clamp if isinstance(clamp, dict) else {}
    clamp_recommended = clamp_payload.get("recommended_max_output_tokens")
    clamp_applied = clamp_payload.get("applied")
    used_max_tokens = _extract_used_max_tokens(_provider_last_call())

    print(f"[RESULT] blocked={blocked} provider_calls_delta={provider_calls_delta}")
    if scenario == "near_cap":
        print(f"[CLAMP] recommended={clamp_recommended} applied={clamp_applied} used_max_tokens={used_max_tokens}")
    if project_id and auth_token:
        _print_incidents(project_id, provider, auth_token)
    else:
        print("[INCIDENTS] skipped (set LLMTBG_PROJECT_ID and LLMTBG_AUTH_TOKEN)")

    if scenario == "allow":
        _assert_line("allow passed", not blocked and provider_calls_delta >= 1 and decision_value == "allow")
    elif scenario == "near_cap":
        _assert_line("near_cap warn triggered", decision_value == "warn" and decision_reason == "near_cap" and not blocked)
        clamp_is_recommended = isinstance(clamp_recommended, int) and clamp_recommended > 0
        clamp_used = clamp_is_recommended and used_max_tokens == clamp_recommended and provider_calls_delta >= 1
        if clamp_used:
            _assert_line("clamp applied / clamp suggested", True)
        else:
            _assert_line("clamp applied / clamp suggested", clamp_is_recommended)
    elif scenario == "cap_breach":
        _assert_line("cap breach blocked", blocked and provider_calls_delta == 0)
    elif scenario == "req_cap_breach":
        _assert_line("req_cap breach blocked", blocked and provider_calls_delta == 0)
        _assert_line("req_cap breach triggered block", blocked and provider_calls_delta == 0)
    elif scenario == "retry_storm":
        _assert_line("retry_storm warn triggered", decision_value == "warn" and decision_reason == "retry_storm" and not blocked)
    elif scenario == "loop_suspect":
        _assert_line("loop_suspect warn triggered", decision_value == "warn" and decision_reason == "loop_suspect" and not blocked)
    elif scenario == "token_explosion":
        _assert_line("token_explosion warn triggered", decision_value == "warn" and decision_reason == "token_explosion" and not blocked)
    elif scenario == "cooldown":
        _assert_line("cooldown active", blocked and provider_calls_delta == 0)
        _assert_line("cooldown active - repeated call blocked", blocked and provider_calls_delta == 0)

    client.close()
    transport.close()


if __name__ == "__main__":
    main()
