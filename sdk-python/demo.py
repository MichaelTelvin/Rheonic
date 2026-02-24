import os
from pathlib import Path
import sys

sdk_src = Path(__file__).resolve().parent / "src"
if str(sdk_src) not in sys.path:
    sys.path.insert(0, str(sdk_src))

from llmtokenburnguard import build_event, capture_event, create_client


def main() -> None:
    # Send one demo event and flush the queue
    ingest_key = os.getenv("LLMTBG_INGEST_KEY")
    if not ingest_key:
        print("LLMTBG_INGEST_KEY is required. Create a key in the dashboard Keys modal first.")
        return

    client = None
    try:
        client = create_client(
            base_url=os.getenv("LLMTBG_BASE_URL"),
            ingest_key=ingest_key,
            protect_enabled=False,
            environment="dev",
            debug=os.getenv("LLMTBG_DEBUG", "").lower() in {"1", "true", "yes"},
        )
        demo_events = [
            ("openai", "gpt-4o-mini", "/chat/completions", 2),
            ("anthropic", "claude-3-5-sonnet", "/v1/messages", 3),
            ("google", "gemini-1.5-pro", "/v1beta/models/generateContent", 4),
        ]
        print("[DEMO] provider scoping active: counters/incidents/decisions are isolated by provider")
        for provider, model, endpoint, total_tokens in demo_events:
            capture_event(
                build_event(
                    provider=provider,
                    model=model,
                    environment="dev",
                    request={"endpoint": endpoint, "input_tokens": 1},
                    response={"output_tokens": 1, "total_tokens": total_tokens, "http_status": 200},
                )
            )
            print(f"[DEMO] queued provider={provider} model={model} endpoint={endpoint}")
        client.flush()
        for provider, _, _, _ in demo_events:
            print(f"[DEMO] flushed provider={provider}")
        print(client.stats())
    finally:
        if client is not None:
            client.close()
        print("done")


if __name__ == "__main__":
    main()
