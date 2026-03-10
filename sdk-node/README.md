# Rheonic Node SDK

The Rheonic Node SDK runs inside your app process, captures provider telemetry, and can request protect preflight decisions before provider calls.

## Install

```bash
npm install rheonic-node
```

## Configuration

- Required: `ingestKey`
- Optional: `baseUrl` (defaults to `RHEONIC_BASE_URL`, else `http://localhost:8000`)
- Optional: `environment` (default `dev`)

Provider/model validation: SDK wrappers fail fast with `RHEONICValidationError` when provider is missing/unsupported or model is missing/empty. Supported providers are `openai`, `anthropic`, and `google`. Model naming is not pattern-validated so future vendor naming changes remain compatible.

## Integration Recommendation

Create one long-lived SDK client at app startup and reuse it for all provider calls. The SDK prewarms tokenizer state and the backend connection on client initialization, so reusing a single client avoids paying protect cold-start cost on every request.

## Integration Path 1: Manual Capture (generic)

```ts
import { buildEvent, createClient } from "rheonic-node";

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
import { createClient, instrumentOpenAI } from "rheonic-node";

const rheonicClient = createClient({ ingestKey: process.env.RHEONIC_INGEST_KEY! });
const openai = instrumentOpenAI(new OpenAI({ apiKey: process.env.OPENAI_API_KEY }), {
  client: rheonicClient,
  endpoint: "/chat/completions",
  feature: "assistant",
});
```

## Integration Path 3: Anthropic and Google wrappers

```ts
import Anthropic from "@anthropic-ai/sdk";
import { GoogleGenerativeAI } from "@google/generative-ai";
import { createClient } from "rheonic-node";

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

Runtime call path:
- SDK instrumentation calls `POST /api/v1/protect/decision` then `POST /api/v1/events`.
- Project mode in dashboard controls decision behavior:
  - Observe: allow only.
  - Protect: allow/warn/block with cooldown.

## Provider SDKs

Install only the provider SDKs you use:

```bash
npm install openai
npm install @anthropic-ai/sdk
npm install @google/generative-ai
```

## Source Repo E2E Utilities

If you are working inside the Rheonic source repository, the demo entrypoints live under:

- `tests/e2e/node/demo.mjs`
- `tests/e2e/node/demo_protect.mjs`
