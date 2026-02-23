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
- Optional: `protect_enabled` (default `False`; when `True`, SDK calls `POST /api/v1/protect/decision` preflight)
- Demo env var: `LLMTBG_INGEST_KEY`

## Integration Path 1: Manual Capture (generic)

```python
import os

from llmtokenburnguard import build_event, capture_event, create_client

create_client(ingest_key=os.environ["LLMTBG_INGEST_KEY"])

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
import os

from openai import OpenAI
from llmtokenburnguard import create_client, instrument_openai

burnguard = create_client(ingest_key=os.environ["LLMTBG_INGEST_KEY"], protect_enabled=True)
openai_client = instrument_openai(
    OpenAI(api_key="..."),
    client=burnguard,
    endpoint="/chat/completions",
    feature="assistant",
)
```

## Verify it works

```bash
export LLMTBG_INGEST_KEY="<copy from Keys modal>"
python demo.py
```

The demo sends one event, flushes, prints stats, and exits.

Backend-down smoke test (must exit cleanly and show failures):

```bash
LLMTBG_BASE_URL=http://127.0.0.1:59999 python demo.py
```

## Check dashboard metrics

After running `python demo.py` with backend/frontend up:
- create/select project in dashboard
- create key in Keys modal, copy it once, and export `LLMTBG_INGEST_KEY`
- open the dashboard (default `http://localhost:5173`)
- confirm metrics changed after ingest

## Manual protect demo

Runs a local protect preflight + provider-stub call flow against:
- backend: `http://localhost:8000`
- provider stub: `http://localhost:8099`

```bash
export LLMTBG_INGEST_KEY="<copy from Keys modal>"
export LLMTBG_SCENARIO=allow   # allow | warn | block
python demo_protect.py
```

Optional overrides:
- `LLMTBG_BACKEND_URL`
- `LLMTBG_PROVIDER_URL`
- `LLMTBG_MAX_TOKENS`
- `LLMTBG_MODEL`
- `LLMTBG_ENVIRONMENT`

Manual mode check:
- Observe (`protect_enabled=False`): only `POST /api/v1/events`
- Protect (`protect_enabled=True`): `POST /api/v1/protect/decision` then `POST /api/v1/events`
