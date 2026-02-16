import { buildEvent, createClient, type Client } from "./index.js";

async function runDemo(): Promise<void> {
  const client: Client = createClient({
    ingestKey: process.env.LLMTBG_INGEST_KEY ?? "p1",
    baseUrl: process.env.LLMTBG_BASE_URL ?? "http://localhost:8000",
    environment: process.env.LLMTBG_ENV ?? "dev",
  });

  await client.captureEvent(
    buildEvent({
      provider: "openai",
      model: "gpt-4o-mini",
      environment: client.environment,
      request: {
        endpoint: "/chat/completions",
        feature: "demo",
      },
      response: {
        latency_ms: 120,
        total_tokens: 42,
        http_status: 200,
      },
    }),
  );

  await client.flush();
  client.close();
}

void runDemo();
