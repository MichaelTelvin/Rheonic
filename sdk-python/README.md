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
except RHEONICBlockedError:
    print("Blocked by protect preflight")
```

Anthropic:

```python
import os
from anthropic import Anthropic
from rheonic import create_client, RHEONICBlockedError

rheonic = create_client(
    base_url=os.environ["RHEONIC_BASE_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
)
anthropic_client = rheonic.instrument_anthropic(
    Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
)

try:
    anthropic_client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=256,
        messages=[{"role": "user", "content": "hello"}],
    )
except RHEONICBlockedError:
    print("Blocked by protect preflight")
```

Google:

```python
import os
import google.generativeai as genai
from rheonic import create_client, RHEONICBlockedError

rheonic = create_client(
    base_url=os.environ["RHEONIC_BASE_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
)
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
google_model = rheonic.instrument_google(genai.GenerativeModel("gemini-1.5-pro"))

try:
    google_model.generate_content("hello")
except RHEONICBlockedError:
    print("Blocked by protect preflight")
```

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
        request={"endpoint": "/chat/completions", "feature": "assistant"},
        response={"total_tokens": 64, "latency_ms": 120, "http_status": 200},
    )
)
```

## Reference

Full quickstart:
- `https://beta.rheonic.dev/quickstart`
