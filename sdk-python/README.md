# LLMTokenBurnGuard Python SDK

This SDK runs inside your app process and sends telemetry events to this LLMTokenBurnGuard service.

## Install

```bash
cd sdk-python
pip install -e .
```

## Configuration

- Required: `ingest_key`
- Optional: `base_url` (defaults to `LLMTBG_BASE_URL` env var, else `http://localhost:8000`)
- Optional: `environment` (default `dev`)

## Integration Path 1: Manual Capture (generic)

```python
from llmtokenburnguard import build_event, capture_event, create_client

create_client(ingest_key="p1")

capture_event(
    build_event(
        provider="openai",
        model="gpt-4o-mini",
        request={"endpoint": "/chat", "input_tokens": 12},
        response={"total_tokens": 32, "latency_ms": 140, "http_status": 200},
    )
)
```

## Integration Path 2: OpenAI instrumentation (convenience wrapper)

```python
from openai import OpenAI
from llmtokenburnguard import create_client, instrument_openai

burnguard = create_client(ingest_key="p1")
openai_client = instrument_openai(
    OpenAI(api_key="..."),
    client=burnguard,
    endpoint="/chat/completions",
    feature="assistant",
)
```

## Verify it works

```bash
python demo.py
```

The demo sends one event, flushes, prints stats, and exits.

Backend-down smoke test (must exit cleanly and show failures):

```bash
LLMTBG_BASE_URL=http://127.0.0.1:59999 python demo.py
```

## Check dashboard metrics

After running `python demo.py` with backend/frontend up:
- open the dashboard (default `http://localhost:5173`)
- select project `p1`
- confirm metrics changed after ingest
