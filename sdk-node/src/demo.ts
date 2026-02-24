import { buildEvent, createClient, type Client } from "./index.js";

async function runDemo(): Promise<void> {
  const ingestKey = process.env.LLMTBG_INGEST_KEY;
  if (!ingestKey) {
    console.error("LLMTBG_INGEST_KEY is required. Create a key in the dashboard Keys modal first.");
    process.exitCode = 1;
    return;
  }

  const client: Client = createClient({
    ingestKey,
    protectEnabled: false,
    environment: process.env.LLMTBG_ENV ?? "dev",
    debug: process.env.LLMTBG_DEBUG === "1" || process.env.LLMTBG_DEBUG === "true",
  });

  const demoEvents = [
    { provider: "openai", model: "gpt-4o-mini", endpoint: "/chat/completions", totalTokens: 42 },
    { provider: "anthropic", model: "claude-3-5-sonnet", endpoint: "/v1/messages", totalTokens: 39 },
    { provider: "google", model: "gemini-1.5-pro", endpoint: "/v1beta/models/generateContent", totalTokens: 36 },
  ] as const;
  console.log("[DEMO] provider scoping active: counters/incidents/decisions are isolated by provider");

  for (const event of demoEvents) {
    await client.captureEvent(
      buildEvent({
        provider: event.provider,
        model: event.model,
        environment: client.environment,
        request: {
          endpoint: event.endpoint,
          feature: "demo",
        },
        response: {
          latency_ms: 120,
          total_tokens: event.totalTokens,
          http_status: 200,
        },
      }),
    );
    console.log(`[DEMO] queued provider=${event.provider} model=${event.model} endpoint=${event.endpoint}`);
  }

  await client.flush();
  for (const event of demoEvents) {
    console.log(`[DEMO] flushed provider=${event.provider}`);
  }
  console.log(client.getStats());
  client.close();
  console.log("done");
}

runDemo().catch((err: unknown) => {
  console.error(err);
  process.exitCode = 1;
});
