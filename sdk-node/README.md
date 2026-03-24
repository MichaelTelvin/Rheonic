# Rheonic Node SDK

Rheonic captures provider telemetry and applies protect preflight decisions before provider calls.

## Install

```bash
npm install @rheonic/sdk
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
    console.log("Blocked by protect preflight");
  }
}
```

Anthropic:

```ts
import Anthropic from "@anthropic-ai/sdk";
import { createClient, RHEONICBlockedError } from "@rheonic/sdk";

const rheonic = createClient({
  baseUrl: process.env.RHEONIC_BASE_URL!,
  ingestKey: process.env.RHEONIC_INGEST_KEY!,
});

const anthropic = rheonic.instrumentAnthropic(new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY! }));

try {
  await anthropic.messages.create({
    model: "claude-3-5-sonnet-latest",
    max_tokens: 256,
    messages: [{ role: "user", content: "hello" }],
  });
} catch (error) {
  if (error instanceof RHEONICBlockedError) {
    console.log("Blocked by protect preflight");
  }
}
```

Google:

```ts
import { GoogleGenerativeAI } from "@google/generative-ai";
import { createClient, RHEONICBlockedError } from "@rheonic/sdk";

const rheonic = createClient({
  baseUrl: process.env.RHEONIC_BASE_URL!,
  ingestKey: process.env.RHEONIC_INGEST_KEY!,
});

const genAI = new GoogleGenerativeAI(process.env.GOOGLE_API_KEY!);
const model = rheonic.instrumentGoogle(genAI.getGenerativeModel({ model: "gemini-1.5-pro" }));

try {
  await model.generateContent("hello");
} catch (error) {
  if (error instanceof RHEONICBlockedError) {
    console.log("Blocked by protect preflight");
  }
}
```

Keep one long-lived SDK client per app process. Initialize it during app startup and reuse it for all capture and instrumentation calls so Rheonic can avoid repeated protect cold-start latency.

## Optional: custom event capture

Use this only if you can't instrument a provider SDK or need custom events.

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
    request: { endpoint: "/chat/completions", feature: "assistant" },
    response: { total_tokens: 64, latency_ms: 120, http_status: 200 },
  }),
);
```

## Reference

Full quickstart:
- `https://beta.rheonic.dev/quickstart`
