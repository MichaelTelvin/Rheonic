# LLMTokenBurnGuard Node SDK

This SDK runs inside your app process and sends telemetry events to this LLMTokenBurnGuard service.

## Install

```bash
cd sdk-node
npm install
```

## Configuration

- Required: `ingestKey`
- Optional: `baseUrl` (defaults to `LLMTBG_BASE_URL` env var, else `http://localhost:8000`)
- Optional: `environment` (default `dev`)

## Integration Path 1: Manual Capture (generic)

```ts
import { buildEvent, captureEvent, createClient } from "./src/index";

createClient({ ingestKey: "p1" });

await captureEvent(
  buildEvent({
    provider: "openai",
    model: "gpt-4o-mini",
    request: { endpoint: "/chat", input_tokens: 12 },
    response: { total_tokens: 32, latency_ms: 140, http_status: 200 },
  }),
);
```

## Integration Path 2: OpenAI instrumentation (convenience wrapper)

```ts
import OpenAI from "openai";
import { createClient, instrumentOpenAI } from "./src/index";

const burnguard = createClient({ ingestKey: "p1" });
const openai = instrumentOpenAI(new OpenAI({ apiKey: process.env.OPENAI_API_KEY }), {
  client: burnguard,
  endpoint: "/chat/completions",
  feature: "assistant",
});
```

## Verify it works

```bash
npm run build
node dist/demo.js
```

The demo sends one event, flushes, and prints SDK stats.

Backend-down smoke test (must exit cleanly and show failures):

```bash
LLMTBG_BASE_URL=http://127.0.0.1:59999 node dist/demo.js
```

Then check dashboard metrics for project `p1` (project id equals ingest key by convention in this MVP).
