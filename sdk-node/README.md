# ⚠️ Status: Development paused.

Rheonic was built as an LLM API layer for cost control and observability in agentic workflows.

The project is currently paused after initial validation attempts.
The system is fully functional, but did not reach product-market fit.
The hosted service is no longer active.
Maintenance has been discontinued for this SDK.

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
    console.log(
      JSON.stringify(
        {
          reason: error.reason,
          retry_after_seconds: error.retry_after_seconds,
          blocked_until: error.blocked_until,
          trace_id: error.trace_id,
          request_id: error.request_id,
        },
        null,
        2,
      ),
    );
  }
}
```

Anthropic:

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

Google:

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

`RHEONICBlockedError.reason` is meant to be operator-relevant. The main values are:
- `tok_cap_breach`
- `req_cap_breach`
- `cooldown_active`
- `fail_closed`

If Protect is `fail_open`, timeout or availability problems stay internal and the provider call continues. If Protect is `fail_closed`, the SDK raises `RHEONICBlockedError` with the feedback fields shown above.

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
    request: { endpoint: "/chat/completions", feature: "assistant", token_explosion_tokens: 64 },
    response: { total_tokens: 64, latency_ms: 120, http_status: 200 },
  }),
);
```

`token_explosion_tokens` is optional. Set it only for custom/manual events when you want token-explosion detection to use the same request-context signal that the SDK instrumentation sends to both protect and ingest.

## Reference

Full quickstart:
- `https://beta.rheonic.dev/quickstart`
