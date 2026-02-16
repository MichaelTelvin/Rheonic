# LLMTokenBurnGuard Python SDK

Minimal Python SDK for async event ingest (fire-and-forget) with OpenAI instrumentation.

## Local install

```bash
cd sdk-python
pip install -e .
```

## Quickstart

```python
from llmtokenburnguard import create_client, build_event, capture_event

client = create_client(
    ingest_key="p1",
    base_url="http://localhost:8000",
    environment="dev",
)

capture_event(
    build_event(
        provider="openai",
        model="gpt-4o-mini",
        environment="dev",
        request={"endpoint": "/chat", "input_tokens": 12},
        response={"total_tokens": 32, "latency_ms": 140, "http_status": 200},
    )
)
```

## OpenAI instrumentation

```python
from openai import OpenAI
from llmtokenburnguard import create_client, instrument_openai

burnguard = create_client(ingest_key="p1", base_url="http://localhost:8000")
openai_client = instrument_openai(
    OpenAI(api_key="..."),
    client=burnguard,
    endpoint="/chat/completions",
    feature="assistant",
)

openai_client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
)
```

## Notes

- Ingest is async fire-and-forget by default.
- Events are queued and flushed periodically in a background thread.
- Best-effort flush is registered with `atexit`.
- For controlled shutdowns, call `client.flush()`.
