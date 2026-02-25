import os
from pathlib import Path
import sys

sdk_src = Path(__file__).resolve().parent / "src"
if str(sdk_src) not in sys.path:
    sys.path.insert(0, str(sdk_src))

from llmtokenburnguard import build_event, capture_event, create_client


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


def main() -> None:
    # Send one demo event and flush the queue
    _load_llmtbg_env_from_dotenv()

    ingest_key = os.getenv("LLMTBG_INGEST_KEY")
    if not ingest_key:
        print("LLMTBG_INGEST_KEY is required. Create a key in the dashboard Keys modal first.")
        return

    provider = (os.getenv("LLMTBG_PROVIDER", "") or "").strip().lower()
    if not provider:
        print("LLMTBG_PROVIDER is required (openai | anthropic | google).")
        return
    if provider not in {"openai", "anthropic", "google"}:
        print(f"LLMTBG_PROVIDER is unsupported: {provider}")
        return

    model = (os.getenv("LLMTBG_MODEL", "") or "").strip()
    if not model:
        print(f"LLMTBG_MODEL is required for provider {provider}.")
        return

    environment = os.getenv("LLMTBG_ENVIRONMENT") or os.getenv("LLMTBG_ENV") or "dev"
    endpoint_by_provider = {
        "openai": "/chat/completions",
        "anthropic": "/v1/messages",
        "google": "/v1beta/models/generateContent",
    }
    endpoint = endpoint_by_provider.get(provider, "/chat/completions")
    total_tokens = int(os.getenv("LLMTBG_TOTAL_TOKENS", "42"))

    client = None
    try:
        client = create_client(
            base_url=os.getenv("LLMTBG_BASE_URL"),
            ingest_key=ingest_key,
            protect_enabled=False,
            environment=environment,
            debug=os.getenv("LLMTBG_DEBUG", "").lower() in {"1", "true", "yes"},
        )
        print("[DEMO] provider scoping active: counters/incidents/decisions are isolated by provider")
        capture_event(
            build_event(
                provider=provider,
                model=model,
                environment=environment,
                request={"endpoint": endpoint, "input_tokens": 1},
                response={"output_tokens": 1, "total_tokens": total_tokens, "http_status": 200},
            )
        )
        print(f"[DEMO] queued provider={provider} model={model} endpoint={endpoint}")
        client.flush()
        print(f"[DEMO] flushed provider={provider}")
        print(client.stats())
    finally:
        if client is not None:
            client.close()
        print("done")


if __name__ == "__main__":
    main()
