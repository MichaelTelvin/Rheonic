# LLMTokenBurnGuard Node SDK

Minimal Node SDK for async event ingest (fire-and-forget) with OpenAI instrumentation.

## Local install

```bash
cd sdk-node
npm install
```

## Quickstart

```ts
import { createClient, captureEvent, buildEvent } from "./src/index";

const client = createClient({
  ingestKey: "p1",
  baseUrl: "http://localhost:8000",
  environment: "dev",
});

await captureEvent(
  buildEvent({
    provider: "openai",
    model: "gpt-4o-mini",
    environment: "dev",
    request: { endpoint: "/chat", input_tokens: 12 },
    response: { total_tokens: 32, latency_ms: 140, http_status: 200 },
  }),
);
```

## OpenAI instrumentation

```ts
import OpenAI from "openai";
import { createClient, instrumentOpenAI } from "./src/index";

const burnguard = createClient({ ingestKey: "p1", baseUrl: "http://localhost:8000" });
const openai = instrumentOpenAI(new OpenAI({ apiKey: process.env.OPENAI_API_KEY }), {
  client: burnguard,
  endpoint: "/chat/completions",
  feature: "assistant",
});

await openai.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "Hello" }],
});
```

## Notes

- Ingest is async fire-and-forget by default.
- Events are queued and flushed in the background.
- Best-effort flush runs on exit (`beforeExit`, `SIGINT`, `SIGTERM`).
- For controlled shutdowns, call `await client.flush()`.
