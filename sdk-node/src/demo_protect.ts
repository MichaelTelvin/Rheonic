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
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const index = line.indexOf("=");
    const key = line.slice(0, index).trim();
    if (!key.startsWith("LLMTBG_")) continue;
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

async function providerCount(): Promise<number> {
  const res = await fetch(`${providerStubUrl}/count`);
  if (!res.ok) throw new Error(`provider_stub_count_failed:${res.status}`);
  const payload = (await res.json()) as { count?: number };
  return Number(payload.count ?? 0);
}

async function resetProvider(): Promise<void> {
  const res = await fetch(`${providerStubUrl}/reset`, { method: "POST" });
  if (!res.ok) throw new Error(`provider_stub_reset_failed:${res.status}`);
}

async function callProviderStub(payload: unknown): Promise<void> {
  const res = await fetch(`${providerStubUrl}/call`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`provider_stub_call_failed:${res.status}`);
}

async function sendIngestEvent(
  ingestKey: string,
  provider: string,
  model: string,
  totalTokens: number,
  feature: string,
  environment: string,
  options?: { status?: string; httpStatus?: number; errorType?: string },
): Promise<void> {
  const payload = {
    ts: new Date().toISOString(),
    provider,
    model,
    environment,
    request: { endpoint: "/chat/completions", feature, input_tokens: 1 },
    response: {
      output_tokens: 1,
      total_tokens: totalTokens,
      latency_ms: 120,
      http_status: options?.httpStatus ?? 200,
      error_type: options?.errorType,
    },
    status: options?.status,
  };
  const response = await fetch(`${backendBaseUrl}/api/v1/events`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Project-Ingest-Key": ingestKey,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`ingest_failed:${response.status}`);
}

async function listOpenIncidents(projectId: string, provider: string, authToken: string): Promise<Array<{ type: string }>> {
  if (!projectId || !authToken) return [];
  const params = new URLSearchParams({ project_id: projectId, status: "open", provider });
  const response = await fetch(`${backendBaseUrl}/api/v1/incidents?${params.toString()}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!response.ok) throw new Error(`list_incidents_failed:${response.status}`);
  const rows = (await response.json()) as Array<{ type: string }>;
  return rows;
}

async function runProviderCall(provider: string, model: string, maxTokens: number, openai: any, anthropic: any, googleModel: any): Promise<boolean> {
  try {
    if (provider === "anthropic") {
      await anthropic.messages.create({
        model,
        messages: [{ role: "user", content: "protect demo request" }],
        max_tokens: maxTokens,
      });
    } else if (provider === "google") {
      await googleModel.generateContent("protect demo request");
    } else {
      await openai.chat.completions.create({
        model,
        messages: [{ role: "user", content: "protect demo request" }],
        max_tokens: maxTokens,
      });
    }
    return false;
  } catch (error) {
    if (error instanceof LLMTBGBlockedError) return true;
    throw error;
  }
}

async function main() {
  const ingestKey = process.env.LLMTBG_INGEST_KEY;
  if (!ingestKey) {
    console.error("LLMTBG_INGEST_KEY is required.");
    process.exit(1);
  }

  const provider = (process.env.LLMTBG_PROVIDER ?? "").trim().toLowerCase();
  if (!provider || !["openai", "anthropic", "google"].includes(provider)) {
    console.error("LLMTBG_PROVIDER is required (openai | anthropic | google).");
    process.exit(1);
  }

  const model = (process.env.LLMTBG_MODEL ?? "").trim();
  if (!model) {
    console.error(`LLMTBG_MODEL is required for provider ${provider}.`);
    process.exit(1);
  }

  const scenario = (process.env.LLMTBG_SCENARIO ?? "allow").toLowerCase();
  const pauseMs = Number(process.env.LLMTBG_STEP_SLEEP_MS ?? 200);
  const env = (process.env.LLMTBG_ENVIRONMENT ?? "").trim() || `protect-${Date.now()}`;
  const authToken = process.env.LLMTBG_AUTH_TOKEN ?? "";
  const projectId = process.env.LLMTBG_PROJECT_ID ?? "";

  await resetProvider();
  const before = await providerCount();

  const client = createClient({
    baseUrl: backendBaseUrl,
    ingestKey,
    protectEnabled: true,
    environment: env,
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

  instrumentOpenAI(openai as any, { client, feature: "manual-protect-demo", environment: env });
  instrumentAnthropic(anthropic as any, { client, feature: "manual-protect-demo", environment: env });
  instrumentGoogle(googleModel as any, { client, feature: "manual-protect-demo", environment: env });

  console.log(`[DEMO] provider=${provider} model=${model} scenario=${scenario}`);
  console.log(`[DEMO] environment=${env}`);

  if (scenario === "near_cap") {
    const seed = Number(process.env.LLMTBG_NEAR_CAP_SEED_TOKENS ?? 1600);
    console.log("[STEP] Seed near-cap traffic then expect warn");
    await sendIngestEvent(ingestKey, provider, model, seed, "near-cap-seed", env);
    await sleep(pauseMs);
  } else if (scenario === "cap_breach") {
    const seed = Number(process.env.LLMTBG_CAP_BREACH_TOKENS ?? 5000);
    console.log("[STEP] Seed cap breach then expect block");
    await sendIngestEvent(ingestKey, provider, model, seed, "cap-breach-seed", env);
    await sleep(pauseMs);
  } else if (scenario === "retry_storm") {
    const count = Number(process.env.LLMTBG_RETRY_STORM_COUNT ?? 6);
    console.log("[STEP] Seed retry storm then expect warn");
    for (let i = 0; i < count; i += 1) {
      await sendIngestEvent(ingestKey, provider, model, 50, `retry-${i + 1}`, env, {
        status: "error",
        httpStatus: 500,
        errorType: "provider_5xx",
      });
      await sleep(pauseMs);
    }
  } else if (scenario === "loop_suspect") {
    const count = Number(process.env.LLMTBG_LOOP_COUNT ?? 7);
    console.log("[STEP] Seed loop suspect then expect warn");
    for (let i = 0; i < count; i += 1) {
      await sendIngestEvent(ingestKey, provider, model, 60, "loop-fixed-signature", env);
      await sleep(pauseMs);
    }
  } else if (scenario === "token_explosion") {
    const seed = Number(process.env.LLMTBG_TOKEN_EXPLOSION_TOKENS ?? 9000);
    console.log("[STEP] Seed token explosion then expect warn");
    await sendIngestEvent(ingestKey, provider, model, seed, "token-explosion-seed", env);
    await sleep(pauseMs);
  }

  const maxTokens = Number(process.env.LLMTBG_MAX_TOKENS ?? 128);
  const blocked = await runProviderCall(provider, model, maxTokens, openai, anthropic, googleModel);
  await client.flush();
  const after = await providerCount();

  console.log(`[RESULT] blocked=${blocked} provider_calls_delta=${after - before}`);

  if (projectId && authToken) {
    const incidents = await listOpenIncidents(projectId, provider, authToken);
    const counts = new Map<string, number>();
    for (const incident of incidents) counts.set(incident.type, (counts.get(incident.type) ?? 0) + 1);
    const compact = Array.from(counts.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${k}=${v}`)
      .join(", ");
    console.log(`[INCIDENTS] open=${incidents.length} types=${compact || "none"}`);
  } else {
    console.log("[INCIDENTS] skipped (set LLMTBG_PROJECT_ID and LLMTBG_AUTH_TOKEN)");
  }

  await client.flush();
  console.log("[DEMO] sdk delivery stats:", client.getStats());
  client.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
