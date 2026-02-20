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
    environment: process.env.LLMTBG_ENV ?? "dev",
    debug: process.env.LLMTBG_DEBUG === "1" || process.env.LLMTBG_DEBUG === "true",
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
        total_tokens: 420,
        http_status: 200,
      },
    }),
  );

  await client.flush();
  console.log(client.getStats());
  client.close();
  console.log("done");
}

runDemo().catch((err: unknown) => {
  console.error(err);
  process.exitCode = 1;
});
