# Rheonic Python SDK

The Rheonic Python SDK runs inside your app process, captures provider telemetry, and can request protect preflight decisions before provider calls.

## Install

Beta prerelease install:

```bash
pip install rheonic-sdk --pre
```

Optional provider extras:

```bash
pip install "rheonic-sdk[openai]"
pip install "rheonic-sdk[anthropic]"
pip install "rheonic-sdk[google]"
pip install "rheonic-sdk[providers]"
```

## Configuration

- Required: `ingest_key`
- Optional for local development: `base_url` (defaults to `RHEONIC_BASE_URL`, else `http://localhost:8000`)
- Optional: `environment` (default `dev`)

For hosted beta, staging, or production deployments, set `RHEONIC_BASE_URL` or pass `base_url` explicitly. The localhost default is intended only for local development.

Compatibility:
- Python 3.11+
- One of the supported provider SDKs: `openai`, `anthropic`, or `google-generativeai`

Beta note:
- Public beta releases may add guardrail fields and provider wrappers before `1.0.0`.

Provider/model validation: SDK wrappers fail fast with `RHEONICValidationError` when provider is missing/unsupported or model is missing/empty. Supported providers are `openai`, `anthropic`, and `google`. Model naming is not pattern-validated so future vendor naming changes remain compatible.

## Integration Recommendation

Create one long-lived SDK client at app startup and reuse it for all provider calls. The SDK now prewarms tokenizer state and the backend connection on client initialization, so reusing a single client avoids first-call protect latency on every request.

## Logging

The SDK emits structured JSON logs to stdout. You do not need to configure file logging.

Example log:

```json
{
  "timestamp": "2026-03-18T09:20:15.145102+00:00",
  "level": "info",
  "service": "sdk-python",
  "env": "staging",
  "trace_id": "f4ac8b6b-6f8d-4f4c-b54f-3c2c2f76a27b",
  "span_id": "9f12db3a1d204f8f",
  "event": "sdk_client_initialized",
  "message": "SDK client initialized",
  "metadata": {}
}
```

Notes:
- backend requests automatically include `X-Trace-ID`,
- SDK logs share that `trace_id` so you can correlate SDK, backend, worker, and webhook activity,
- sensitive fields such as API keys and tokens are redacted.

## Integration Path 1: Manual Capture (generic)

```python
import os

from rheonic import build_event, create_client

client = create_client(
    base_url=os.environ["RHEONIC_BASE_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
)

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

Minimal protect preflight usage:

```python
decision = client.protect(
    provider="openai",
    model="gpt-4o-mini",
    feature="assistant",
    input_tokens_estimate=32,
    max_output_tokens=256,
)
```

## Integration Path 2: OpenAI instrumentation (convenience wrapper)

```python
import os

from openai import OpenAI
from rheonic import create_client, instrument_openai

rheonic_client = create_client(
    base_url=os.environ["RHEONIC_BASE_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
)
openai_client = instrument_openai(
    OpenAI(api_key="..."),
    client=rheonic_client,
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

client = create_client(
    base_url=os.environ["RHEONIC_BASE_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
)

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

Runtime call path:
- SDK instrumentation calls `POST /api/v1/protect/decision` then `POST /api/v1/events`.
- Project mode in dashboard controls decision behavior:
  - Observe: allow only.
  - Protect: allow/warn/block with cooldown.

## Provider SDKs

Install only the provider SDKs you actually use, either directly or through extras:

```bash
pip install openai
pip install anthropic
pip install google-generativeai
```

Beta prereleases use PEP 440 prerelease format such as `0.2.0b1`.
