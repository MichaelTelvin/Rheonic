import { createClient, instrumentAnthropic, instrumentGoogle, instrumentOpenAI, LLMTBGBlockedError } from "./index.js";
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

loadLlmtbgEnvFromDotenv();

const backendBaseUrl = process.env.LLMTBG_BACKEND_URL ?? "http://localhost:8000";
const providerStubUrl = process.env.LLMTBG_PROVIDER_URL ?? "http://localhost:8099";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function printProviderStubHelp(): void {
  console.error(`Provider stub is unreachable at ${providerStubUrl}.`);
  console.error("Start it with `python3 tests/e2e/provider_stub.py` or set LLMTBG_PROVIDER_URL to a reachable endpoint.");
}

async function providerCount(): Promise<number> {
  const res = await fetch(`${providerStubUrl}/count`);
  if (!res.ok) {
    throw new Error(`provider_stub_count_failed:${res.status}`);
  }
  const payload = (await res.json()) as { count?: number };
  return Number(payload.count ?? 0);
}

async function resetProvider(): Promise<void> {
  const res = await fetch(`${providerStubUrl}/reset`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`provider_stub_reset_failed:${res.status}`);
  }
}

async function callProviderStub(payload: unknown): Promise<void> {
  const res = await fetch(`${providerStubUrl}/call`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`provider_stub_call_failed:${res.status}`);
  }
}

async function sendIngestEvent(ingestKey: string, provider: string, model: string, totalTokens: number, feature: string): Promise<void> {
  const now = new Date().toISOString();
  const payload = {
    ts: now,
    provider,
    model,
    environment: process.env.LLMTBG_ENV ?? "dev",
    request: {
      endpoint: "/chat/completions",
      feature,
      input_tokens: 1,
    },
    response: {
      output_tokens: 1,
      total_tokens: totalTokens,
      latency_ms: 120,
      http_status: 200,
    },
  };
  const response = await fetch(`${backendBaseUrl}/api/v1/events`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Project-Ingest-Key": ingestKey,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`ingest_failed:${response.status}`);
  }
}

async function listOpenIncidents(projectId: string, provider: string, authToken: string): Promise<Array<{ id: string; severity: string }>> {
  const params = new URLSearchParams({ project_id: projectId, status: "open" });
  if (provider) {
    params.set("provider", provider);
  }
  const response = await fetch(`${backendBaseUrl}/api/v1/incidents?${params.toString()}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!response.ok) {
    throw new Error(`list_incidents_failed:${response.status}`);
  }
  const rows = (await response.json()) as Array<{ id: string; severity: string }>;
  return rows;
}

async function resolveIncident(incidentId: string, authToken: string): Promise<void> {
  const response = await fetch(`${backendBaseUrl}/api/v1/incidents/${incidentId}/resolve`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${authToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
  });
  if (!response.ok) {
    throw new Error(`resolve_failed:${response.status}`);
  }
}

async function printWebhookStatus(projectId: string, authToken: string): Promise<void> {
  const response = await fetch(`${backendBaseUrl}/api/v1/projects/${encodeURIComponent(projectId)}/webhook`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!response.ok) {
    console.log(`[OBSERVE] webhook status unavailable (status=${response.status})`);
    return;
  }
  const payload = (await response.json()) as {
    webhook_last_delivery_status?: string | null;
    webhook_last_delivery_at?: string | null;
  };
  console.log(
    `[OBSERVE] webhook last_delivery=${payload.webhook_last_delivery_status ?? "none"} at ${payload.webhook_last_delivery_at ?? "n/a"}`,
  );
}

async function runProtectDecisionHarness(options: {
  provider: string;
  model: string;
  scenario: string;
  openai: any;
  anthropic: any;
  googleModel: any;
  client: ReturnType<typeof createClient>;
}): Promise<void> {
  const { provider, model, scenario, openai, anthropic, googleModel, client } = options;
  const maxTokens = Number(process.env.LLMTBG_MAX_TOKENS ?? (scenario === "block" ? 2000 : 128));

  const before = await providerCount();

  console.log("\n[STEP] Protect decision preflight");
  console.log(`[EXPECT] scenario=${scenario} should produce allow/warn/block before provider call`);

  try {
    if (provider === "anthropic") {
      await anthropic.messages.create({
        model,
        messages: [{ role: "user", content: `Protect harness request. scenario=${scenario}` }],
        max_tokens: maxTokens,
      });
    } else if (provider === "google") {
      await googleModel.generateContent(`Protect harness request. scenario=${scenario}`);
    } else {
      await openai.chat.completions.create({
        model,
        messages: [{ role: "user", content: `Protect harness request. scenario=${scenario}` }],
        max_tokens: maxTokens,
      });
    }
    console.log(`[OBSERVE] provider call executed for scenario=${scenario}`);
  } catch (error) {
    if (error instanceof LLMTBGBlockedError) {
      console.log(`[OBSERVE] blocked by protect preflight for scenario=${scenario}`);
    } else {
      throw error;
    }
  }

  await client.flush();
  const after = await providerCount();
  console.log(`[OBSERVE] provider_calls_delta=${after - before}`);
}

async function runWebhookHarness(options: {
  ingestKey: string;
  provider: string;
  model: string;
  authToken: string;
  projectId: string;
  pauseMs: number;
}): Promise<void> {
  const { ingestKey, provider, model, authToken, projectId, pauseMs } = options;
  console.log("\n[STEP] Warm-up behavior");
  console.log("[EXPECT] tiny early traffic should not create ratio-based incident");
  await sendIngestEvent(ingestKey, provider, model, 42, "harness-warmup-1");
  await sleep(pauseMs);
  await sendIngestEvent(ingestKey, provider, model, 42, "harness-warmup-2");

  console.log("\n[STEP] High-open + webhook");
  console.log("[EXPECT] high incident opens and webhook incident.high is dispatched");
  for (let i = 0; i < 8; i += 1) {
    await sendIngestEvent(ingestKey, provider, model, 100, `harness-baseline-${i + 1}`);
    await sleep(pauseMs);
  }
  await sendIngestEvent(ingestKey, provider, model, 60000, "harness-high-open");

  console.log("\n[STEP] Escalation + webhook");
  console.log("[EXPECT] repeated hits escalate severity to high and dispatch incident.high (source=escalation)");
  await sendIngestEvent(ingestKey, provider, model, 60000, "harness-escalation-1");
  await sleep(pauseMs);
  await sendIngestEvent(ingestKey, provider, model, 60000, "harness-escalation-2");

  if (authToken && projectId) {
    const incidents = await listOpenIncidents(projectId, provider, authToken);
    console.log(`[OBSERVE] open incidents in scope=${incidents.length}`);
    const first = incidents[0];
    if (first) {
      console.log("\n[STEP] Manual resolve + webhook");
      console.log("[EXPECT] incident.resolved webhook dispatched with resolved_by=manual");
      await resolveIncident(first.id, authToken);
    }
    console.log("\n[STEP] Auto-resolve + webhook");
    console.log("[EXPECT] after inactivity cooldown, auto-resolve emits incident.resolved with resolved_by=auto");
    console.log("[OBSERVE] wait incident_auto_close_seconds, then check incidents/webhook status");
    await printWebhookStatus(projectId, authToken);
  } else {
    console.log("[OBSERVE] set LLMTBG_AUTH_TOKEN + LLMTBG_PROJECT_ID to verify manual resolve and webhook status from API");
  }
}

async function main() {
  const ingestKey = process.env.LLMTBG_INGEST_KEY;
  if (!ingestKey) {
    console.error("LLMTBG_INGEST_KEY is required (create/copy a key from the dashboard).");
    process.exit(1);
  }
  const provider = (process.env.LLMTBG_PROVIDER ?? "").trim().toLowerCase();
  if (!provider) {
    console.error("LLMTBG_PROVIDER is required (openai | anthropic | google).");
    process.exit(1);
  }
  if (!["openai", "anthropic", "google"].includes(provider)) {
    console.error(`LLMTBG_PROVIDER is unsupported: ${provider}`);
    process.exit(1);
  }
  const model = (process.env.LLMTBG_MODEL ?? "").trim();
  if (!model) {
    console.error(`LLMTBG_MODEL is required for provider ${provider}.`);
    process.exit(1);
  }

  const harnessCase = (process.env.LLMTBG_HARNESS_CASE ?? "protect").toLowerCase();
  const scenario = (process.env.LLMTBG_SCENARIO ?? "allow").toLowerCase();
  const pauseMs = Number(process.env.LLMTBG_STEP_SLEEP_MS ?? 800);
  const authToken = process.env.LLMTBG_AUTH_TOKEN ?? "";
  const projectId = process.env.LLMTBG_PROJECT_ID ?? "";

  try {
    await resetProvider();
  } catch {
    printProviderStubHelp();
    process.exit(1);
  }

  const client = createClient({
    baseUrl: backendBaseUrl,
    ingestKey,
    protectEnabled: true,
    environment: process.env.LLMTBG_ENV ?? "dev",
    debug: process.env.LLMTBG_DEBUG === "1" || process.env.LLMTBG_DEBUG === "true",
    flushIntervalMs: 60_000,
  });

  const openai = {
    chat: {
      completions: {
        create: async (payload: any) => {
          await callProviderStub(payload);
          return { model: payload.model, usage: { total_tokens: 10 } };
        },
      },
    },
  };
  const anthropic = {
    messages: {
      create: async (payload: any) => {
        await callProviderStub(payload);
        return { model: payload.model, usage: { input_tokens: 6, output_tokens: 4 } };
      },
    },
  };
  const googleModel = {
    model,
    generateContent: async (payload: any) => {
      const requestPayload = typeof payload === "string" ? { prompt: payload } : payload;
      await callProviderStub(requestPayload);
      return { response: { usageMetadata: { totalTokenCount: 10 } } };
    },
  };

  instrumentOpenAI(openai as any, { client, feature: "manual-protect-demo" });
  instrumentAnthropic(anthropic as any, { client, feature: "manual-protect-demo" });
  instrumentGoogle(googleModel as any, { client, feature: "manual-protect-demo" });

  console.log(`[DEMO] provider=${provider} model=${model} harness=${harnessCase}`);
  console.log("[DEMO] provider scoping active: counters/incidents/decisions are isolated by provider");

  try {
    if (harnessCase === "all") {
      await runProtectDecisionHarness({ provider, model, scenario, openai, anthropic, googleModel, client });
      await runWebhookHarness({ ingestKey, provider, model, authToken, projectId, pauseMs });
    } else if (harnessCase === "protect") {
      await runProtectDecisionHarness({ provider, model, scenario, openai, anthropic, googleModel, client });
    } else if (harnessCase === "webhooks") {
      await runWebhookHarness({ ingestKey, provider, model, authToken, projectId, pauseMs });
    } else {
      console.error(`Unsupported LLMTBG_HARNESS_CASE: ${harnessCase}`);
      process.exitCode = 1;
    }
  } catch (err) {
    printProviderStubHelp();
    console.error("[ERROR]", err);
    process.exitCode = 1;
  } finally {
    await client.flush();
    console.log("[DEMO] sdk delivery stats:", client.getStats());
    client.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
