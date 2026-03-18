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
export RHEONIC_BACKEND_URL="http://localhost:8000"
```

## 3. Install an SDK
Node:

```bash
npm install rheonic-node
```

Python:

```bash
pip install rheonic
```

## 4. Send Your First Event
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
    response: { total_tokens: 64, latency_ms: 120, http_status: 200 },
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
        response={"total_tokens": 64, "latency_ms": 120, "http_status": 200},
    )
)
```

Keep one long-lived SDK client per app process. Initialize it during app startup and reuse it for all capture/instrumentation calls. Rheonic prewarms tokenizer state and the backend connection when the client starts, so reusing that client avoids repeated protect cold-start latency.

## 4.1 SDK Logging
The SDK emits structured JSON logs to stdout. You do not need to configure file logging.

Typical SDK log object:

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

What to expect:
- backend requests automatically carry `X-Trace-ID`,
- SDK logs share that `trace_id` so you can correlate app, backend, worker, and webhook activity,
- sensitive fields such as tokens or API keys are redacted and should not appear in logs.

If you already collect stdout logs into Grafana Loki or another aggregator, the SDK logs are ready to ingest as-is.

## 5. Verify in the Dashboard
After your first event:
- `Dashboard` should show non-zero request and token activity.
- `Projects` should list the providers that have sent traffic.
- `Incidents` remains empty until detector conditions are met.

If nothing appears:
- confirm the selected project matches the ingest key you created,
- confirm `RHEONIC_BACKEND_URL` points to your backend,
- confirm the SDK call completed successfully.

## 6. Enable Protect Mode
When you are ready to enforce runtime limits:
1. Open `Protect`.
2. Set request and token caps.
3. Choose a fail mode.
4. Save the settings and switch from Observe to Protect.

Rheonic will continue collecting telemetry in both modes. The difference is that Protect mode can return `warn` or `block` before a provider call is made.

## 7. Configure Alerts
Open `Alerts` to:
- send notifications to your account email,
- enable a webhook destination,
- test webhook delivery before relying on it in production.

## Next Steps
- Read `Integrations` for provider wrappers and runtime behavior.
- Read `Protect Mode` before rollout.
- Read `Alerts` if you want email or webhook notifications.
