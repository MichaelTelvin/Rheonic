from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from llmtokenburnguard.client import Client
from llmtokenburnguard.protect_engine import LLMTBGBlockedError
from llmtokenburnguard.providers.anthropic_adapter import instrument_anthropic
from llmtokenburnguard.providers.google_adapter import instrument_google
from llmtokenburnguard.providers.openai_adapter import instrument_openai


def _load_llmtbg_env_from_dotenv() -> None:
    # Load LLMTBG_* values from repo .env so demos work without manual export.
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
        os.environ[key] = value.strip().strip("\"").strip("'")


_load_llmtbg_env_from_dotenv()

BACKEND_BASE_URL = os.getenv("LLMTBG_BACKEND_URL", "http://localhost:8000")
PROVIDER_STUB_URL = os.getenv("LLMTBG_PROVIDER_URL", "http://localhost:8099")


class LoggingHttpClient:
    # Minimal transport wrapper for SDK client that logs protect decision payload/response.

    def __init__(self, timeout_s: float) -> None:
        self._client = httpx.Client(timeout=timeout_s)
        self.last_decision_request: dict[str, Any] | None = None
        self.last_decision_response: dict[str, Any] | None = None

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str], timeout: float | None = None) -> httpx.Response:
        if url.endswith("/api/v1/protect/decision"):
            self.last_decision_request = dict(json)
            print("=== PROTECT DECISION REQUEST ===")
            print(json_dumps(self.last_decision_request))
            response = self._client.post(url, json=json, headers=headers, timeout=timeout)
            payload: dict[str, Any]
            try:
                parsed = response.json()
                payload = parsed if isinstance(parsed, dict) else {"raw": parsed}
            except Exception:
                payload = {"status_code": response.status_code, "body": response.text}
            self.last_decision_response = payload
            print("=== PROTECT DECISION RESPONSE ===")
            print(json_dumps(payload))
            return response
        return self._client.post(url, json=json, headers=headers, timeout=timeout)

    def close(self) -> None:
        self._client.close()


@dataclass
class ProviderCounts:
    before: int
    after: int

    @property
    def delta(self) -> int:
        return self.after - self.before


def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def require_tokenizer() -> None:
    try:
        import tiktoken  # noqa: F401
    except Exception as exc:  # pragma: no cover - runtime environment dependent
        print("ERROR: tiktoken is required for token estimation. Install sdk-python dependencies and retry.")
        print(f"Details: {exc}")
        sys.exit(1)


def provider_reset() -> None:
    try:
        httpx.post(f"{PROVIDER_STUB_URL}/reset", timeout=3.0).raise_for_status()
    except Exception:
        return


def provider_count() -> int | None:
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


def make_openai_stub() -> Any:
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


def make_anthropic_stub() -> Any:
    class Messages:
        @staticmethod
        def create(**kwargs: Any) -> Any:
            httpx.post(f"{PROVIDER_STUB_URL}/call", json=kwargs, timeout=3.0).raise_for_status()
            usage = type("Usage", (), {"input_tokens": 6, "output_tokens": 4})()
            return type("Response", (), {"model": kwargs.get("model"), "usage": usage})()

    class AnthropicStub:
        messages = Messages()

    return AnthropicStub()


def make_google_stub() -> Any:
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


def print_provider_stub_help() -> None:
    print(f"ERROR: provider stub is unreachable at {PROVIDER_STUB_URL}")
    print("Start it with `python3 tests/e2e/provider_stub.py` or set LLMTBG_PROVIDER_URL to a reachable endpoint.")


def main() -> None:
    ingest_key = os.getenv("LLMTBG_INGEST_KEY")
    if not ingest_key:
        print("LLMTBG_INGEST_KEY is required.")
        sys.exit(1)

    require_tokenizer()

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
    environment = os.getenv("LLMTBG_ENVIRONMENT", "dev")
    max_tokens_env = os.getenv("LLMTBG_MAX_TOKENS")
    max_tokens = int(max_tokens_env) if max_tokens_env else (2000 if scenario == "block" else 128)

    transport = LoggingHttpClient(timeout_s=5.0)
    client = Client(
        ingest_key=ingest_key,
        base_url=BACKEND_BASE_URL,
        protect_enabled=True,
        environment=environment,
        flush_interval_s=60.0,
        http_client=transport,
    )

    openai = make_openai_stub()
    anthropic = make_anthropic_stub()
    google = make_google_stub()
    google.model_name = model
    instrument_openai(openai, client=client, feature="manual-protect-demo", environment=environment)
    instrument_anthropic(anthropic, client=client, feature="manual-protect-demo", environment=environment)
    instrument_google(google, client=client, feature="manual-protect-demo", environment=environment)

    provider_reset()
    before = provider_count()
    if before is None:
        print_provider_stub_help()
        client.close()
        transport.close()
        return

    blocked = False
    warned = False
    print(f"[DEMO] provider={provider} model={model} scenario={scenario}")
    print("[DEMO] provider scoping active: counters/incidents/decisions are isolated by provider")
    try:
        if provider == "anthropic":
            anthropic.messages.create(
                model=model,
                messages=[{"role": "user", "content": f"Manual protect demo request. scenario={scenario}."}],
                max_tokens=max_tokens,
            )
        elif provider == "google":
            google.generate_content(f"Manual protect demo request. scenario={scenario}.")
        else:
            openai.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": f"Manual protect demo request. scenario={scenario}.",
                    }
                ],
                max_tokens=max_tokens,
            )
        decision = transport.last_decision_response or {}
        warned = decision.get("decision") == "warn"
        if warned:
            print(f"[WARN] Provider call executed (provider={provider}, scenario={scenario}).")
        else:
            print(f"[OK] Provider call executed (provider={provider}, scenario={scenario}).")
    except LLMTBGBlockedError:
        blocked = True
        print(f"[BLOCKED] LLMTBGBlockedError thrown (provider={provider}, scenario={scenario}).")
    except httpx.ConnectError:
        print_provider_stub_help()
        return
    finally:
        client.flush()
        client.close()
        transport.close()

    after = provider_count()
    if before is not None and after is not None:
        counts = ProviderCounts(before=before, after=after)
        print({"provider_calls_delta": counts.delta, "before": counts.before, "after": counts.after})

    estimate = None
    if isinstance(transport.last_decision_request, dict):
        estimate = transport.last_decision_request.get("input_tokens_estimate")
    print(f"input_tokens_estimate sent: {estimate if estimate is not None else '(omitted)'}")

    if blocked:
        return


if __name__ == "__main__":
    main()
