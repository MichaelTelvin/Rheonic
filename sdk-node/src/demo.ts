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

  const provider = (process.env.LLMTBG_PROVIDER ?? "").trim().toLowerCase();
  if (!provider) {
    console.error("LLMTBG_PROVIDER is required (openai | anthropic | google).");
    process.exitCode = 1;
    return;
  }
  if (!["openai", "anthropic", "google"].includes(provider)) {
    console.error(`LLMTBG_PROVIDER is unsupported: ${provider}`);
    process.exitCode = 1;
    return;
  }

  const model = (process.env.LLMTBG_MODEL ?? "").trim();
  if (!model) {
    console.error(`LLMTBG_MODEL is required for provider ${provider}.`);
    process.exitCode = 1;
    return;
  }

  const endpointByProvider: Record<string, string> = {
    openai: "/chat/completions",
    anthropic: "/v1/messages",
    google: "/v1beta/models/generateContent",
  };
  const endpoint = endpointByProvider[provider] ?? "/chat/completions";
  const totalTokens = Number(process.env.LLMTBG_TOTAL_TOKENS ?? 42);

  console.log("[DEMO] provider scoping active: counters/incidents/decisions are isolated by provider");

  await client.captureEvent(
    buildEvent({
      provider,
      model,
      environment: client.environment,
      request: {
        endpoint,
        feature: "demo",
      },
      response: {
        latency_ms: 120,
        total_tokens: totalTokens,
        http_status: 200,
      },
    }),
  );
  console.log(`[DEMO] queued provider=${provider} model=${model} endpoint=${endpoint}`);

  await client.flush();
  console.log(`[DEMO] flushed provider=${provider}`);
  console.log(client.getStats());
  client.close();
  console.log("done");
}

runDemo().catch((err: unknown) => {
  console.error(err);
  process.exitCode = 1;
});
