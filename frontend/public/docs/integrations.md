# Integrations

Rheonic supports two integration styles:
- manual event capture,
- provider instrumentation with preflight protection.

## Supported SDKs and Providers
- Node SDK
- Python SDK
- OpenAI
- Anthropic
- Google

## Required Configuration
- `RHEONIC_INGEST_KEY`
- `RHEONIC_BACKEND_URL`

Optional:
- environment label such as `production` or `staging`,
- provider API keys used by your own provider client.

## Runtime Recommendation
- Create one long-lived SDK client at app startup and reuse it across requests.
- Do not create a new Rheonic client per provider call.
- The SDK prewarms tokenizer state and the backend connection on startup so the first protected call is not penalized repeatedly.

## Manual Capture
Use manual capture when you want to send telemetry without wrapping a provider SDK.

Node:

```ts
import { createClient, buildEvent } from "rheonic-node";

const client = createClient({
  baseUrl: process.env.RHEONIC_BACKEND_URL!,
  ingestKey: process.env.RHEONIC_INGEST_KEY!,
});

await client.captureEvent(
  buildEvent({
    provider: "openai",
    model: "gpt-4o-mini",
    request: { endpoint: "/chat/completions", feature: "assistant" },
    response: { total_tokens: 128, latency_ms: 180, http_status: 200 },
  }),
);
```

Python:

```python
import os
from rheonic import create_client, build_event

client = create_client(
    base_url=os.environ["RHEONIC_BACKEND_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
)

client.capture_event(
    build_event(
        provider="openai",
        model="gpt-4o-mini",
        request={"endpoint": "/chat/completions", "feature": "assistant"},
        response={"total_tokens": 128, "latency_ms": 180, "http_status": 200},
    )
)
```

## Provider Instrumentation
With instrumentation, the SDK performs a protect preflight before the provider call and then sends an event after the call completes.

### OpenAI Example

```ts
import OpenAI from "openai";
import { createClient, instrumentOpenAI, RHEONICBlockedError } from "rheonic-node";

const rheonic = createClient({
  baseUrl: process.env.RHEONIC_BACKEND_URL!,
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
    console.log("Blocked by Rheonic");
  }
}
```

## Runtime Call Path
Instrumented requests follow this order:
1. SDK requests a protect decision from `POST /api/v1/protect/decision`.
2. If the decision is `allow` or `warn`, the provider call proceeds.
3. The SDK sends telemetry to `POST /api/v1/events`.

In Observe mode, the preflight still runs but the backend returns allow-only behavior.

## Provider Scope
Within one project, Rheonic tracks counters and protect decisions separately for each provider. Dashboard endpoints aggregate totals across providers unless you apply a provider filter.

## Validation
The SDK validates:
- provider name,
- model presence,
- basic request shape for wrapped providers.

If validation fails, the SDK raises a client-side validation error before sending the request.

## Choose the Right Integration
- Use manual capture if you only need telemetry.
- Use provider instrumentation if you want preflight warnings, blocks, and automatic event capture.
