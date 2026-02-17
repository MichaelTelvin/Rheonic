"""Minimal SDK demo script."""

import os
from pathlib import Path
import sys

sdk_src = Path(__file__).resolve().parent / "src"
if str(sdk_src) not in sys.path:
    sys.path.insert(0, str(sdk_src))

from llmtokenburnguard import build_event, capture_event, create_client


def main() -> None:
    """Send one demo event and flush the queue."""
    ingest_key = os.getenv("LLMTBG_INGEST_KEY")
    if not ingest_key:
        print("LLMTBG_INGEST_KEY is required. Create a key in the dashboard Keys modal first.")
        return

    client = None
    try:
        client = create_client(
            base_url=os.getenv("LLMTBG_BASE_URL"),
            ingest_key=ingest_key,
            environment="dev",
            debug=os.getenv("LLMTBG_DEBUG", "").lower() in {"1", "true", "yes"},
        )
        capture_event(
            build_event(
                provider="openai",
                model="gpt-4o-mini",
                environment="dev",
                request={"endpoint": "/demo", "input_tokens": 1},
                response={"output_tokens": 1, "total_tokens": 2, "http_status": 200},
            )
        )
        client.flush()
        print(client.stats())
    finally:
        if client is not None:
            client.close()
        print("done")


if __name__ == "__main__":
    main()
