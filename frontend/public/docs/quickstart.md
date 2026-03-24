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
import { createClient, instrumentOpenAI, RHEONICBlockedError } from "rheonic-node";

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
    console.log("Blocked by protect preflight");
  }
}
```

Python OpenAI:

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

Keep one long-lived SDK client per app process. Initialize it during app startup and reuse it for all capture and instrumentation calls so Rheonic can avoid repeated protect cold-start latency.

## 5. Verify in Observe mode

Make one provider call. Open the dashboard and confirm traffic appears.

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
import { createClient, buildEvent } from "rheonic-node";

const client = createClient({
  baseUrl: process.env.RHEONIC_BASE_URL!,
  ingestKey: process.env.RHEONIC_INGEST_KEY!,
});

await client.captureEvent(
  buildEvent({
    provider: "openai",
    model: "gpt-4o-mini",
    request: { endpoint: "/chat/completions", feature: "assistant" },
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
        request={"endpoint": "/chat/completions", "feature": "assistant"},
        response={"total_tokens": 64, "latency_ms": 120, "http_status": 200},
    )
)
```
