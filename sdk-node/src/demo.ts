import { buildEvent, createClient, type Client } from "./index.js";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

function loadLlmtbgEnvFromDotenv(): void {
  const currentFile = fileURLToPath(import.meta.url);
  const dotenvPath = resolve(dirname(currentFile), "../../.env");
  let content = "";
  try {
    content = readFileSync(dotenvPath, "utf8");
  } catch {
    return;
  }
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const index = line.indexOf("=");
    const key = line.slice(0, index).trim();
    if (!key.startsWith("LLMTBG_")) continue;
    const value = line.slice(index + 1).trim().replace(/^['"]|['"]$/g, "");
    process.env[key] = value;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchRealtimeSnapshot(projectId: string, authToken: string, provider: string, phase: string): Promise<void> {
  if (!authToken || !projectId) {
    console.log(`[SNAPSHOT] ${phase}: (snapshot skipped: no auth token/project id)`);
    return;
  }
  const params = new URLSearchParams({ project_id: projectId });
  if (provider !== "all") params.set("provider", provider);
  const response = await fetch(`http://localhost:8000/api/v1/metrics/realtime?${params.toString()}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!response.ok) {
    console.log(`[SNAPSHOT] ${phase}: unavailable (status=${response.status})`);
    return;
  }
  const payload = (await response.json()) as Record<string, unknown>;
  console.log(`[SNAPSHOT] ${phase}: req60=${payload.requests_60s} tok60=${payload.tokens_60s}`);
}

async function fetchIncidentSummary(projectId: string, authToken: string, provider: string): Promise<void> {
  if (!authToken || !projectId) {
    console.log("[OBSERVE] incidents: (skipped: no auth token/project id)");
    return;
  }
  const params = new URLSearchParams({ project_id: projectId, status: "open" });
  if (provider !== "all") params.set("provider", provider);
  const response = await fetch(`http://localhost:8000/api/v1/incidents?${params.toString()}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!response.ok) {
    console.log(`[OBSERVE] incidents summary unavailable (status=${response.status})`);
    return;
  }
  const incidents = (await response.json()) as Array<{ type?: string }>;
  const counts = new Map<string, number>();
  for (const incident of incidents) {
    const t = (incident.type ?? "unknown").toString();
    counts.set(t, (counts.get(t) ?? 0) + 1);
  }
  const compact = Array.from(counts.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`)
    .join(", ");
  console.log(`[OBSERVE] incidents open=${incidents.length} types=${compact || "none"}`);
}

async function printPhase(phase: string, projectId: string, authToken: string, provider: string): Promise<void> {
  await fetchRealtimeSnapshot(projectId, authToken, provider, phase);
  await fetchIncidentSummary(projectId, authToken, provider);
}

async function sendEvent(
  client: Client,
  provider: string,
  model: string,
  endpoint: string,
  totalTokens: number,
  feature: string,
  options?: { httpStatus?: number; errorType?: string },
): Promise<void> {
  await client.captureEvent(
    buildEvent({
      provider,
      model,
      environment: client.environment,
      request: { endpoint, feature },
      response: {
        latency_ms: 120,
        total_tokens: totalTokens,
        http_status: options?.httpStatus ?? 200,
        error_type: options?.errorType,
      },
    }),
  );
}

function printUsageExamples(): void {
  console.log("Example:");
  console.log("  LLMTBG_PROVIDER=openai");
  console.log("  LLMTBG_MODEL=gpt-4o-mini");
  console.log("  LLMTBG_DEMO_CASE=steady|retry_storm|loop_suspect|token_explosion|cap_breach|all");
  console.log("  LLMTBG_STEP_SLEEP_MS=200");
  console.log("  LLMTBG_RETRY_STORM_COUNT=6");
  console.log("  LLMTBG_LOOP_COUNT=7");
  console.log("  LLMTBG_TOKEN_EXPLOSION_TOKENS=9000");
  console.log("  LLMTBG_CAP_BREACH_TOKENS=4000");
  console.log("  Optional snapshot/incident summary:");
  console.log("  LLMTBG_AUTH_TOKEN=<jwt> LLMTBG_PROJECT_ID=<project_id>");
}

async function runDemo(): Promise<void> {
  loadLlmtbgEnvFromDotenv();

  const ingestKey = process.env.LLMTBG_INGEST_KEY;
  if (!ingestKey) {
    console.error("LLMTBG_INGEST_KEY is required. Create a key in dashboard Keys page.");
    printUsageExamples();
    process.exitCode = 1;
    return;
  }

  const provider = (process.env.LLMTBG_PROVIDER ?? "").trim().toLowerCase();
  if (!provider || !["openai", "anthropic", "google"].includes(provider)) {
    console.error("LLMTBG_PROVIDER is required (openai | anthropic | google).");
    printUsageExamples();
    process.exitCode = 1;
    return;
  }

  const model = (process.env.LLMTBG_MODEL ?? "").trim();
  if (!model) {
    console.error(`LLMTBG_MODEL is required for provider ${provider}.`);
    printUsageExamples();
    process.exitCode = 1;
    return;
  }

  const endpointByProvider: Record<string, string> = {
    openai: "/chat/completions",
    anthropic: "/v1/messages",
    google: "/v1beta/models/generateContent",
  };
  const endpoint = endpointByProvider[provider] ?? "/chat/completions";
  const demoCase = (process.env.LLMTBG_DEMO_CASE ?? "steady").toLowerCase();
  const stepSleepMs = Number(process.env.LLMTBG_STEP_SLEEP_MS ?? 200);
  const retryStormCount = Number(process.env.LLMTBG_RETRY_STORM_COUNT ?? 6);
  const loopCount = Number(process.env.LLMTBG_LOOP_COUNT ?? 7);
  const tokenExplosionTokens = Number(process.env.LLMTBG_TOKEN_EXPLOSION_TOKENS ?? 9000);
  const capBreachTokens = Number(process.env.LLMTBG_CAP_BREACH_TOKENS ?? 4000);

  const authToken = process.env.LLMTBG_AUTH_TOKEN ?? "";
  const projectId = process.env.LLMTBG_PROJECT_ID ?? "";
  const environment = (process.env.LLMTBG_ENVIRONMENT ?? "").trim() || `demo-${Date.now()}`;

  const client: Client = createClient({
    ingestKey,
    protectEnabled: false,
    environment,
    debug: process.env.LLMTBG_DEBUG === "1" || process.env.LLMTBG_DEBUG === "true",
  });

  console.log(`[DEMO] provider=${provider} model=${model} case=${demoCase}`);
  console.log(`[DEMO] environment=${environment}`);
  console.log(
    `[DEMO] params retry_storm_count=${retryStormCount} loop_count=${loopCount} token_explosion_tokens=${tokenExplosionTokens} cap_breach_tokens=${capBreachTokens} step_sleep_ms=${stepSleepMs}`,
  );

  const runSteady = async (): Promise<void> => {
    console.log("\n[STEP] Steady traffic / no anomaly");
    await sendEvent(client, provider, model, endpoint, 42, "steady-1");
    await sleep(stepSleepMs);
    await sendEvent(client, provider, model, endpoint, 42, "steady-2");
    await client.flush();
    await printPhase("steady", projectId, authToken, provider);
  };

  const runRetryStorm = async (): Promise<void> => {
    console.log("\n[STEP] Retry storm");
    for (let i = 0; i < retryStormCount; i += 1) {
      await sendEvent(client, provider, model, endpoint, 50, `retry-${i + 1}`, {
        httpStatus: 500,
        errorType: "provider_5xx",
      });
      await sleep(stepSleepMs);
    }
    await client.flush();
    await printPhase("retry_storm", projectId, authToken, provider);
  };

  const runLoopSuspect = async (): Promise<void> => {
    console.log("\n[STEP] Loop suspect");
    for (let i = 0; i < loopCount; i += 1) {
      await sendEvent(client, provider, model, endpoint, 60, "loop-fixed-signature");
      await sleep(stepSleepMs);
    }
    await client.flush();
    await printPhase("loop_suspect", projectId, authToken, provider);
  };

  const runTokenExplosion = async (): Promise<void> => {
    console.log("\n[STEP] Token explosion");
    await sendEvent(client, provider, model, endpoint, tokenExplosionTokens, "token-explosion");
    await client.flush();
    await printPhase("token_explosion", projectId, authToken, provider);
  };

  const runCapBreach = async (): Promise<void> => {
    console.log("\n[STEP] Cap breach logging (observe)");
    await sendEvent(client, provider, model, endpoint, capBreachTokens, "cap-breach");
    await client.flush();
    await printPhase("cap_breach", projectId, authToken, provider);
  };

  if (demoCase === "all") {
    await runSteady();
    await runRetryStorm();
    await runLoopSuspect();
    await runTokenExplosion();
    await runCapBreach();
  } else if (demoCase === "steady") {
    await runSteady();
  } else if (demoCase === "retry_storm") {
    await runRetryStorm();
  } else if (demoCase === "loop_suspect") {
    await runLoopSuspect();
  } else if (demoCase === "token_explosion") {
    await runTokenExplosion();
  } else if (demoCase === "cap_breach") {
    await runCapBreach();
  } else {
    console.error(`Unsupported LLMTBG_DEMO_CASE: ${demoCase}`);
    printUsageExamples();
    process.exitCode = 1;
  }

  console.log("\n[DONE] observe demo complete");
  console.log(client.getStats());
  client.close();
}

runDemo().catch((err: unknown) => {
  console.error(err);
  process.exitCode = 1;
});
