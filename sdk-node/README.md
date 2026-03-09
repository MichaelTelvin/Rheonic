# Rheonic Node SDK

This SDK runs inside your app process and sends telemetry events to this Rheonic service.

## Install

```bash
cd sdk-node
npm install
```

## Configuration

- Required: `ingestKey`
- Optional: `baseUrl` (defaults to `RHEONIC_BASE_URL` env var, else `http://localhost:8000`)
- Optional: `environment` (default `dev`)
- Demo env var: `RHEONIC_INGEST_KEY`

Provider/model validation: SDK wrappers fail fast with `RHEONICValidationError` when provider is missing/unsupported or model is missing/empty. Supported providers are `openai`, `anthropic`, and `google`. Model naming is not pattern-validated so future vendor naming changes remain compatible.

## Integration Recommendation

Create one long-lived SDK client at app startup and reuse it for all provider calls. The SDK prewarms tokenizer state and the backend connection on client initialization, so reusing a single client avoids paying protect cold-start cost on every request.

## Integration Path 1: Manual Capture (generic)

```ts
import { buildEvent, captureEvent, createClient } from "./src/index";

const client = createClient({ ingestKey: process.env.RHEONIC_INGEST_KEY! });

await client.captureEvent(
  buildEvent({
    provider: "openai",
    model: "gpt-4o-mini",
    request: { endpoint: "/chat", input_tokens: 12 },
    response: { total_tokens: 32, latency_ms: 140, http_status: 200 },
  }),
);
```

Initialize `client` once during app startup, then reuse that same instance for manual capture and provider instrumentation.

## Integration Path 2: OpenAI instrumentation (convenience wrapper)

```ts
import OpenAI from "openai";
import { createClient, instrumentOpenAI } from "./src/index";

const burnguard = createClient({ ingestKey: process.env.RHEONIC_INGEST_KEY! });
const openai = instrumentOpenAI(new OpenAI({ apiKey: process.env.OPENAI_API_KEY }), {
  client: burnguard,
  endpoint: "/chat/completions",
  feature: "assistant",
});
```

## Integration Path 3: Anthropic and Google wrappers

```ts
import Anthropic from "@anthropic-ai/sdk";
import { GoogleGenerativeAI } from "@google/generative-ai";
import { createClient } from "./src/index";

const client = createClient({ ingestKey: process.env.RHEONIC_INGEST_KEY! });

const anthropic = client.instrumentAnthropic(new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY }));
await anthropic.messages.create({
  model: "claude-3-5-sonnet-latest",
  max_tokens: 256,
  messages: [{ role: "user", content: "Hello Claude" }],
});

const genAI = new GoogleGenerativeAI(process.env.GOOGLE_API_KEY!);
const googleModel = client.instrumentGoogle(genAI.getGenerativeModel({ model: "gemini-1.5-pro" }));
await googleModel.generateContent("Hello Google model");
```

## Verify it works

```bash
npm run build
export RHEONIC_INGEST_KEY="<copy from Keys modal>"
node dist/demo.js
```

The demo sends one event, flushes, and prints SDK stats.

Backend-down smoke test (must exit cleanly and show failures):

```bash
RHEONIC_BASE_URL=http://127.0.0.1:59999 node dist/demo.js
```

Before running the demo:
1. Create/select a project in the dashboard.
2. Open `Keys` modal and create a key.
3. Copy the plaintext key once and export `RHEONIC_INGEST_KEY`.

Then check dashboard metrics for the selected project.

Runtime call path:
- SDK instrumentation calls `POST /api/v1/protect/decision` then `POST /api/v1/events`.
- Project mode in dashboard controls decision behavior:
  - Observe: allow only.
  - Protect: allow/warn/block with cooldown.
