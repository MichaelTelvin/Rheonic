# ⚠️ Status: Development paused.

Rheonic was built as an LLM API layer for cost control and observability in agentic workflows.

The project is currently paused after initial validation attempts.
The system is fully functional, but did not reach product-market fit.
The hosted service is no longer active.
Maintenance has been discontinued for this SDK.

# Rheonic Python SDK

Rheonic captures provider telemetry and applies protect preflight decisions before provider calls.

## Install

```bash
pip install rheonic-sdk --pre
```

## Required environment variables

```bash
RHEONIC_INGEST_KEY=<your_project_ingest_key>
RHEONIC_BASE_URL=<value_shown_in_dashboard>
```

## Instrument provider calls

Wrap your provider SDK once.

Telemetry is captured automatically after each provider call.

Enforcement follows Project mode in the dashboard (`Observe` / `Protect`).

OpenAI:

```python
import json
import os
from openai import OpenAI
from rheonic import create_client, instrument_openai, RHEONICBlockedError

rheonic = create_client(
    base_url=os.environ["RHEONIC_BASE_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
)
openai_client = instrument_openai(
    OpenAI(api_key=os.environ["OPENAI_API_KEY"]),
    client=rheonic,
    endpoint="/chat/completions",
    feature="assistant",
)

try:
    openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=256,
    )
except RHEONICBlockedError as error:
    print(json.dumps({
        "reason": error.reason,
        "retry_after_seconds": error.retry_after_seconds,
        "blocked_until": error.blocked_until,
        "trace_id": error.trace_id,
        "request_id": error.request_id,
    }, indent=2))
```

Anthropic:

```python
import json
import os
from anthropic import Anthropic
from rheonic import create_client, instrument_anthropic, RHEONICBlockedError

rheonic = create_client(
    base_url=os.environ["RHEONIC_BASE_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
)
anthropic_client = instrument_anthropic(
    Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]),
    client=rheonic,
    endpoint="/v1/messages",
    feature="assistant",
)

try:
    anthropic_client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=256,
        messages=[{"role": "user", "content": "hello"}],
    )
except RHEONICBlockedError as error:
    print(json.dumps({
        "reason": error.reason,
        "retry_after_seconds": error.retry_after_seconds,
        "blocked_until": error.blocked_until,
        "trace_id": error.trace_id,
        "request_id": error.request_id,
    }, indent=2))
```

Google:

```python
import json
import os
from google import genai
from google.genai import types
from rheonic import create_client, instrument_google, RHEONICBlockedError

rheonic = create_client(
    base_url=os.environ["RHEONIC_BASE_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
)
google_client = instrument_google(
    genai.Client(api_key=os.environ["GOOGLE_API_KEY"]),
    client=rheonic,
    endpoint="/v1beta/models/generateContent",
    feature="assistant",
)

try:
    google_client.models.generate_content(
        model="gemini-1.5-pro",
        contents="hello",
        config=types.GenerateContentConfig(max_output_tokens=256),
    )
except RHEONICBlockedError as error:
    print(json.dumps({
        "reason": error.reason,
        "retry_after_seconds": error.retry_after_seconds,
        "blocked_until": error.blocked_until,
        "trace_id": error.trace_id,
        "request_id": error.request_id,
    }, indent=2))
```

`RHEONICBlockedError.reason` is meant to be operator-relevant. The main values are:
- `tok_cap_breach`
- `req_cap_breach`
- `cooldown_active`
- `fail_closed`

If Protect is `fail_open`, timeout or availability problems stay internal and the provider call continues. If Protect is `fail_closed`, the SDK raises `RHEONICBlockedError` with the feedback fields shown above.

Keep one long-lived SDK client per app process. Initialize it during app startup and reuse it for all capture and instrumentation calls so Rheonic can avoid repeated protect cold-start latency.

## Optional: custom event capture

Use this only if you can't instrument a provider SDK or need custom events.

```python
import os
from rheonic import create_client, build_event

client = create_client(
    base_url=os.environ["RHEONIC_BASE_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
)

client.capture_event(
    build_event(
        provider="openai",
        model="gpt-4o-mini",
        request={"endpoint": "/chat/completions", "feature": "assistant", "token_explosion_tokens": 64},
        response={"total_tokens": 64, "latency_ms": 120, "http_status": 200},
    )
)
```

`token_explosion_tokens` is optional. Set it only for custom/manual events when you want token-explosion detection to use the same request-context signal that the SDK instrumentation sends to both protect and ingest.

## Reference

Full quickstart:
- `https://beta.rheonic.dev/quickstart`

## Support

support@rheonic.dev
