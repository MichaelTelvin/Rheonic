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
    if (!line || line.startsWith("#") || !line.includes("=")) {
      continue;
    }
    const index = line.indexOf("=");
    const key = line.slice(0, index).trim();
    if (!key.startsWith("LLMTBG_")) {
      continue;
    }
    const value = line.slice(index + 1).trim().replace(/^['"]|['"]$/g, "");
    process.env[key] = value;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchIncidentSummary(projectId: string, authToken: string, provider: string): Promise<void> {
  const params = new URLSearchParams({ project_id: projectId, status: "open" });
  if (provider !== "all") {
    params.set("provider", provider);
  }
  const response = await fetch(`http://localhost:8000/api/v1/incidents?${params.toString()}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!response.ok) {
    console.log(`[OBSERVE] incidents summary unavailable (status=${response.status})`);
    return;
  }
  const incidents = (await response.json()) as Array<{ severity: string; type: string }>;
  const counts = { low: 0, medium: 0, high: 0 };
  for (const incident of incidents) {
    if (incident.severity === "low") counts.low += 1;
    if (incident.severity === "medium") counts.medium += 1;
    if (incident.severity === "high") counts.high += 1;
  }
  console.log(`[OBSERVE] incidents open=${incidents.length} low=${counts.low} medium=${counts.medium} high=${counts.high}`);
}

async function sendEvent(client: Client, provider: string, model: string, endpoint: string, totalTokens: number, feature: string): Promise<void> {
  await client.captureEvent(
    buildEvent({
      provider,
      model,
      environment: client.environment,
      request: { endpoint, feature },
      response: {
        latency_ms: 120,
        total_tokens: totalTokens,
        http_status: 200,
      },
    }),
  );
}

async function runDemo(): Promise<void> {
  loadLlmtbgEnvFromDotenv();

  const ingestKey = process.env.LLMTBG_INGEST_KEY;
  if (!ingestKey) {
    console.error("LLMTBG_INGEST_KEY is required. Create a key in the dashboard Keys page first.");
    process.exitCode = 1;
    return;
  }

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
  const demoCase = (process.env.LLMTBG_DEMO_CASE ?? "warmup").toLowerCase();
  const stepSleepMs = Number(process.env.LLMTBG_STEP_SLEEP_MS ?? 800);
  const baselineEvents = Number(process.env.LLMTBG_BASELINE_EVENTS ?? 8);
  const baselineTokens = Number(process.env.LLMTBG_BASELINE_TOKENS ?? 100);
  const spikeTokens = Number(process.env.LLMTBG_SPIKE_TOKENS ?? 60000);
  const escalationHits = Number(process.env.LLMTBG_ESCALATION_HITS ?? 3);

  const authToken = process.env.LLMTBG_AUTH_TOKEN ?? "";
  const projectId = process.env.LLMTBG_PROJECT_ID ?? "";

  const client: Client = createClient({
    ingestKey,
    protectEnabled: false,
    environment: process.env.LLMTBG_ENV ?? "dev",
    debug: process.env.LLMTBG_DEBUG === "1" || process.env.LLMTBG_DEBUG === "true",
  });

  console.log(`[DEMO] provider=${provider} model=${model} case=${demoCase}`);
  console.log("[DEMO] provider scoping active: counters/incidents/decisions are isolated by provider");

  const runWarmup = async (): Promise<void> => {
    console.log("\n[STEP] Warm-up baseline behavior");
    console.log("[EXPECT] tiny early traffic should not create ratio-based incident");
    await sendEvent(client, provider, model, endpoint, 42, "demo-warmup-1");
    await sleep(stepSleepMs);
    await sendEvent(client, provider, model, endpoint, 42, "demo-warmup-2");
    await client.flush();
  };

  const runSpike = async (): Promise<void> => {
    console.log("\n[STEP] True spike detection");
    console.log("[EXPECT] baseline-ready ratio+delta or warm-up early-abs should open incident");
    for (let i = 0; i < baselineEvents; i += 1) {
      await sendEvent(client, provider, model, endpoint, baselineTokens, `demo-baseline-${i + 1}`);
      await sleep(stepSleepMs);
    }
    await sendEvent(client, provider, model, endpoint, spikeTokens, "demo-spike");
    await client.flush();
  };

  const runEscalation = async (): Promise<void> => {
    console.log("\n[STEP] Escalation behavior");
    console.log("[EXPECT] repeat spike hits in escalation windows promote severity");
    for (let i = 0; i < escalationHits; i += 1) {
      await sendEvent(client, provider, model, endpoint, spikeTokens, `demo-escalation-${i + 1}`);
      await sleep(stepSleepMs);
    }
    await client.flush();
  };

  const runLifecycle = async (): Promise<void> => {
    console.log("\n[STEP] Incident lifecycle");
    console.log("[EXPECT] open -> update/escalate -> resolve (manual or auto-close)");
    await sendEvent(client, provider, model, endpoint, spikeTokens, "demo-lifecycle-open");
    await sleep(stepSleepMs);
    await sendEvent(client, provider, model, endpoint, spikeTokens, "demo-lifecycle-update");
    await client.flush();

    if (authToken && projectId) {
      await fetchIncidentSummary(projectId, authToken, provider);
      console.log("[OBSERVE] for manual resolve, use Dashboard Incidents page or call /api/v1/incidents/{id}/resolve");
      console.log("[OBSERVE] auto-resolve happens after incident_auto_close_seconds inactivity");
    } else {
      console.log("[OBSERVE] set LLMTBG_AUTH_TOKEN + LLMTBG_PROJECT_ID to print incident summary from API");
    }
  };

  if (demoCase === "all") {
    await runWarmup();
    await runSpike();
    await runEscalation();
    await runLifecycle();
  } else if (demoCase === "warmup") {
    await runWarmup();
  } else if (demoCase === "spike") {
    await runSpike();
  } else if (demoCase === "escalation") {
    await runEscalation();
  } else if (demoCase === "lifecycle") {
    await runLifecycle();
  } else {
    console.error(`Unsupported LLMTBG_DEMO_CASE: ${demoCase}`);
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
