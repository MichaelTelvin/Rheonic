# Quickstart

Use this guide to get a project sending data into Rheonic and verify that telemetry appears in the dashboard.

## 1. Create a Project
1. Open the dashboard and go to `Projects`.
2. Create a project for your app or environment.
3. Select that project so the dashboard, keys, incidents, and protect settings all point to the same context.

You can also delete a project later from the `Protect` page if you need to remove that environment and its associated project data.

## 2. Create an Ingest Key
1. Open `Keys`.
2. Create a key such as `production` or `staging`.
3. Copy the plaintext value when it is shown.

Set it in your app environment:

```bash
export RHEONIC_INGEST_KEY="your-ingest-key"
export RHEONIC_BASE_URL="http://localhost:8000"
```

## 3. Install an SDK
Node:

```bash
npm install @rheonic/sdk
```

Python:

```bash
pip install rheonic-sdk --pre
```

## 4. Instrument provider calls

Wrap your provider SDK once.

Telemetry is captured automatically after each provider call.

Enforcement follows Project mode in the dashboard (Observe / Protect).

Node OpenAI:

```ts
import OpenAI from "openai";
import { createClient, instrumentOpenAI, RHEONICBlockedError } from "@rheonic/sdk";

const rheonic = createClient({
  baseUrl: process.env.RHEONIC_BASE_URL!,
  ingestKey: process.env.RHEONIC_INGEST_KEY!,
});

const openai = instrumentOpenAI(new OpenAI({ apiKey: process.env.OPENAI_API_KEY! }), {
  client: rheonic,
  endpoint: "/chat/completions",
  feature: "assistant",
});

try {
  await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [{ role: "user", content: "hello" }],
    max_tokens: 256,
  });
} catch (error) {
  if (error instanceof RHEONICBlockedError) {
    console.log(JSON.stringify({
      reason: error.reason,
      retry_after_seconds: error.retry_after_seconds,
      blocked_until: error.blocked_until,
      trace_id: error.trace_id,
      request_id: error.request_id,
    }, null, 2));
  }
}
```

Node Anthropic:

```ts
import Anthropic from "@anthropic-ai/sdk";
import { createClient, instrumentAnthropic, RHEONICBlockedError } from "@rheonic/sdk";

const rheonic = createClient({
  baseUrl: process.env.RHEONIC_BASE_URL!,
  ingestKey: process.env.RHEONIC_INGEST_KEY!,
});

const anthropic = instrumentAnthropic(new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY! }), {
  client: rheonic,
  endpoint: "/v1/messages",
  feature: "assistant",
});

try {
  await anthropic.messages.create({
    model: "claude-3-5-sonnet-latest",
    max_tokens: 256,
    messages: [{ role: "user", content: "hello" }],
  });
} catch (error) {
  if (error instanceof RHEONICBlockedError) {
    console.log(JSON.stringify({
      reason: error.reason,
      retry_after_seconds: error.retry_after_seconds,
      blocked_until: error.blocked_until,
      trace_id: error.trace_id,
      request_id: error.request_id,
    }, null, 2));
  }
}
```

Node Google:

```ts
import { GoogleGenAI } from "@google/genai";
import { createClient, instrumentGoogle, RHEONICBlockedError } from "@rheonic/sdk";

const rheonic = createClient({
  baseUrl: process.env.RHEONIC_BASE_URL!,
  ingestKey: process.env.RHEONIC_INGEST_KEY!,
});

const ai = instrumentGoogle(new GoogleGenAI({ apiKey: process.env.GOOGLE_API_KEY! }), {
  client: rheonic,
  endpoint: "/v1beta/models/generateContent",
  feature: "assistant",
});

try {
  await ai.models.generateContent({
    model: "gemini-1.5-pro",
    contents: "hello",
    config: {
      maxOutputTokens: 256,
    },
  });
} catch (error) {
  if (error instanceof RHEONICBlockedError) {
    console.log(JSON.stringify({
      reason: error.reason,
      retry_after_seconds: error.retry_after_seconds,
      blocked_until: error.blocked_until,
      trace_id: error.trace_id,
      request_id: error.request_id,
    }, null, 2));
  }
}
```

Python OpenAI:

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

Python Anthropic:

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

Python Google:

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

When Protect blocks a call, the SDK raises `RHEONICBlockedError` with agent-visible feedback. The main reasons are:
- `tok_cap_breach`
- `req_cap_breach`
- `cooldown_active`
- `fail_closed`

Typical block feedback:

```json
{
  "reason": "req_cap_breach",
  "retry_after_seconds": 42,
  "blocked_until": "2026-03-31T09:20:00Z",
  "trace_id": "e8e1d3f0-8f54-4f89-9d4d-8ef58d71d9b1",
  "request_id": "5f7c7bf11d0a43c28b4da6d97c9d145f"
}
```

If Protect is `fail_open`, timeout or availability problems stay internal and the provider call continues. If Protect is `fail_closed`, the block reason is `fail_closed`.

Keep one long-lived SDK client per app process. Initialize it during app startup and reuse it for all capture and instrumentation calls so Rheonic can avoid repeated protect cold-start latency.

## 5. Verify in Observe mode

Make one provider call. Open the dashboard and confirm traffic appears.

Incidents surface detector states such as failed retry storms, rapid repeated loop sequences, and sudden request-context growth when those patterns appear. Token-explosion defaults are intentionally conservative so healthy RAG and agent flows are less likely to be tagged as anomalous, and tiny prompt jumps should not be mistaken for explosions.

Dashboard path: `Dashboard → Metrics` or `Incidents`

## 6. Set request and token limits

In Project Settings, configure request and token limits per provider.

Dashboard path: `Dashboard → Project Settings → Limits`

## 7. Enable Protect mode

Switch Project mode from Observe to Protect to activate enforcement.

Dashboard path: `Dashboard → Project Settings → Mode`

## 8. Optional: custom event capture

Use this only if you can't instrument a provider SDK or need custom events.

Node:

```ts
import { createClient, buildEvent } from "@rheonic/sdk";

const client = createClient({
  baseUrl: process.env.RHEONIC_BASE_URL!,
  ingestKey: process.env.RHEONIC_INGEST_KEY!,
});

await client.captureEvent(
  buildEvent({
    provider: "openai",
    model: "gpt-4o-mini",
    request: { endpoint: "/chat/completions", feature: "assistant", token_explosion_tokens: 64 },
    response: { total_tokens: 64, latency_ms: 120, http_status: 200 },
  }),
);
```

Python:

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
