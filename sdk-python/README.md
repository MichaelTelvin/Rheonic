# Rheonic Python SDK

This SDK runs inside your app process and sends telemetry events to this Rheonic service.

## Install

```bash
cd sdk-python
pip install -e .
```

## Configuration

- Required: `ingest_key`
- Optional: `base_url` (defaults to `RHEONIC_BASE_URL` env var, else `http://localhost:8000`)
- Optional: `environment` (default `dev`)
- Demo env var: `RHEONIC_INGEST_KEY`

Provider/model validation: SDK wrappers fail fast with `RHEONICValidationError` when provider is missing/unsupported or model is missing/empty. Supported providers are `openai`, `anthropic`, and `google`. Model naming is not pattern-validated so future vendor naming changes remain compatible.

## Integration Recommendation

Create one long-lived SDK client at app startup and reuse it for all provider calls. The SDK now prewarms tokenizer state and the backend connection on client initialization, so reusing a single client avoids first-call protect latency on every request.

## Integration Path 1: Manual Capture (generic)

```python
import os

from rheonic import build_event, create_client

client = create_client(ingest_key=os.environ["RHEONIC_INGEST_KEY"])

client.capture_event(
    build_event(
        provider="openai",
        model="gpt-4o-mini",
        request={"endpoint": "/chat", "input_tokens": 12},
        response={"total_tokens": 32, "latency_ms": 140, "http_status": 200},
    )
)
```

Initialize `client` once during app startup, then reuse that same instance when you capture events or instrument provider SDKs.

## Integration Path 2: OpenAI instrumentation (convenience wrapper)

```python
import os

from openai import OpenAI
from rheonic import create_client, instrument_openai

burnguard = create_client(ingest_key=os.environ["RHEONIC_INGEST_KEY"])
openai_client = instrument_openai(
    OpenAI(api_key="..."),
    client=burnguard,
    endpoint="/chat/completions",
    feature="assistant",
)
```

## Integration Path 3: Anthropic and Google wrappers

```python
import os
from anthropic import Anthropic
import google.generativeai as genai

from rheonic import create_client

client = create_client(ingest_key=os.environ["RHEONIC_INGEST_KEY"])

anthropic_client = client.instrument_anthropic(Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]))
anthropic_client.messages.create(
    model="claude-3-5-sonnet-latest",
    max_tokens=256,
    messages=[{"role": "user", "content": "Hello Claude"}],
)

genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
google_model = client.instrument_google(genai.GenerativeModel("gemini-1.5-pro"))
google_model.generate_content("Hello Google model")
```

## Verify it works

```bash
export RHEONIC_INGEST_KEY="<copy from Keys modal>"
python demo.py
```

The demo sends one event, flushes, prints stats, and exits.

Backend-down smoke test (must exit cleanly and show failures):

```bash
RHEONIC_BASE_URL=http://127.0.0.1:59999 python demo.py
```

## Check dashboard metrics

After running `python demo.py` with backend/frontend up:
- create/select project in dashboard
- create key in Keys modal, copy it once, and export `RHEONIC_INGEST_KEY`
- open the dashboard (default `http://localhost:5173`)
- confirm metrics changed after ingest

## Manual protect demo

Runs a local protect preflight + provider-stub call flow against:
- backend: `http://localhost:8000`
- provider stub: `http://localhost:8099`

```bash
export RHEONIC_INGEST_KEY="<copy from Keys modal>"
export RHEONIC_SCENARIO=allow   # allow | warn | block
python demo_protect.py
```

Optional overrides:
- `RHEONIC_BACKEND_URL`
- `RHEONIC_PROVIDER_URL`
- `RHEONIC_MAX_TOKENS`
- `RHEONIC_MODEL`
- `RHEONIC_ENVIRONMENT`

Runtime call path:
- SDK instrumentation calls `POST /api/v1/protect/decision` then `POST /api/v1/events`.
- Project mode in dashboard controls decision behavior:
  - Observe: allow only.
  - Protect: allow/warn/block with cooldown.
