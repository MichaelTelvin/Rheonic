import { buildEvent, createClient, type Client } from "./index.js";

async function runDemo(): Promise<void> {
  const client: Client = createClient({
    ingestKey: process.env.LLMTBG_INGEST_KEY ?? "p1",
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
        total_tokens: 42,
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
