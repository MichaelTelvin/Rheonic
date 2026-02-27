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
let lastProviderCall: Record<string, unknown> | null = null;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function envInt(name: string, fallback: number): number {
  const raw = process.env[name];
  if (typeof raw !== "string" || raw.trim() === "") return fallback;
  const parsed = Number.parseInt(raw.trim(), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
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
  if (payload && typeof payload === "object") {
    lastProviderCall = payload as Record<string, unknown>;
  }
  const res = await fetch(`${providerStubUrl}/call`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`provider_stub_call_failed:${res.status}`);
}

function providerLastCall(): Record<string, unknown> | null {
  return lastProviderCall;
}

function extractUsedMaxTokens(payload: Record<string, unknown> | null): number | null {
  if (!payload) return null;
  const value = payload.max_tokens;
  if (typeof value === "number" && Number.isFinite(value)) return Math.floor(value);
  return null;
}

function assertLine(label: string, passed: boolean): void {
  // deterministic, human-readable checks.
  console.log(passed ? `[ASSERT] ${label}` : `[ASSERT] ${label} (FAILED)`);
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
  const status = options?.status ?? "ok";
  const httpStatus = options?.httpStatus ?? 200;
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
      http_status: httpStatus,
      ...(options?.errorType ? { error_type: options.errorType } : {}),
    },
    status,
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

async function listOpenIncidents(
  projectId: string,
  provider: string,
  authToken: string,
): Promise<Array<{ type: string; evidence?: { near_cap_type?: string } }>> {
  if (!projectId || !authToken) return [];
  const params = new URLSearchParams({ project_id: projectId, status: "open", provider });
  const response = await fetch(`${backendBaseUrl}/api/v1/incidents?${params.toString()}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      console.log(`[INCIDENTS] skipped (${response.status} auth error; update LLMTBG_AUTH_TOKEN)`);
      return [];
    }
    throw new Error(`list_incidents_failed:${response.status}`);
  }
  const rows = (await response.json()) as Array<{ type: string; evidence?: { near_cap_type?: string } }>;
  return rows;
}

async function getProjectReqCap(projectId: string, authToken: string): Promise<number | null> {
  if (!projectId || !authToken) return null;
  const response = await fetch(`${backendBaseUrl}/api/v1/projects/${projectId}/protect`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!response.ok) return null;
  const payload = (await response.json()) as { protect_max_req_per_min?: unknown };
  const value = payload.protect_max_req_per_min;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 1) return null;
  return Math.floor(value);
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
  const pauseMs = envInt("LLMTBG_STEP_SLEEP_MS", 200);
  const protectDecisionTimeoutMs = envInt("LLMTBG_PROTECT_DECISION_TIMEOUT_MS", 100);
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
    protectDecisionTimeoutMs,
  });

  let lastDecisionContext: Record<string, unknown> | null = null;
  let lastDecisionValue = "";
  let lastDecisionReason = "";
  let lastClampRecommended: number | null = null;
  let lastClampApplied: boolean | null = null;
  const originalEvaluateProtectDecision = client.evaluateProtectDecision.bind(client);
  client.evaluateProtectDecision = async (context: Parameters<typeof originalEvaluateProtectDecision>[0]) => {
    lastDecisionContext = context as unknown as Record<string, unknown>;
    console.log("=== PROTECT DECISION REQUEST ===");
    console.log(JSON.stringify(context, null, 2));
    let decision;
    try {
      decision = await originalEvaluateProtectDecision(context);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.log(`=== PROTECT DECISION ERROR === ${message}`);
      throw error;
    }
    lastDecisionValue = decision.decision;
    lastDecisionReason = decision.reason;
    lastClampRecommended = decision.clamp?.recommended_max_output_tokens ?? null;
    lastClampApplied = decision.clamp?.applied ?? null;
    console.log("=== PROTECT DECISION RESPONSE ===");
    console.log(JSON.stringify(decision, null, 2));
    return decision;
  };

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

  const decisionFeature = scenario === "loop_suspect" ? "loop-fixed-signature" : "manual-protect-demo";
  instrumentOpenAI(openai as any, { client, feature: decisionFeature, environment: env });
  instrumentAnthropic(anthropic as any, { client, feature: decisionFeature, environment: env });
  instrumentGoogle(googleModel as any, { client, feature: decisionFeature, environment: env });

  console.log(`[DEMO] provider=${provider} model=${model} scenario=${scenario}`);
  console.log(`[DEMO] environment=${env}`);
  console.log(`[DEMO] protect_decision_timeout_ms=${protectDecisionTimeoutMs}`);
  console.log(`[DEMO] decision_feature=${decisionFeature}`);
  const maxTokens = envInt("LLMTBG_MAX_TOKENS", 128);
  let callMaxTokens = maxTokens;
  console.log(`[DEMO] max_tokens(before call)=${maxTokens}`);

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
  } else if (scenario === "req_cap_breach") {
    let count = envInt("LLMTBG_REQ_CAP_BREACH_COUNT", 6);
    const reqTokens = envInt("LLMTBG_CAP_BREACH_REQ_TOKENS", 1);
    const reqCap = await getProjectReqCap(projectId, authToken);
    if (typeof reqCap === "number") {
      count = Math.max(count, reqCap + 1);
    }
    console.log(`[STEP] Seed req cap breach then expect block (events=${count}, req_cap=${reqCap ?? "unknown"})`);
    for (let i = 0; i < count; i += 1) {
      await sendIngestEvent(ingestKey, provider, model, reqTokens, `req-cap-breach-${i + 1}`, env);
      if (pauseMs > 0) {
        await sleep(pauseMs);
      }
    }
    console.log(`[STEP] req_cap_breach ingest events sent=${count} (provider_calls_delta tracks provider calls only)`);
  } else if (scenario === "retry_storm") {
    const count = envInt("LLMTBG_RETRY_STORM_COUNT", 6);
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
    const count = envInt("LLMTBG_LOOP_COUNT", 7);
    console.log("[STEP] Seed loop suspect then expect warn");
    for (let i = 0; i < count; i += 1) {
      await sendIngestEvent(ingestKey, provider, model, 60, "loop-fixed-signature", env);
      await sleep(pauseMs);
    }
  } else if (scenario === "token_explosion") {
    const seed = envInt("LLMTBG_TOKEN_EXPLOSION_TOKENS", 9000);
    console.log("[STEP] Seed token explosion then expect warn");
    await sendIngestEvent(ingestKey, provider, model, seed, "token-explosion-seed", env);
    callMaxTokens = Math.max(maxTokens, seed);
    console.log(`[STEP] token_explosion call max_tokens=${callMaxTokens}`);
    await sleep(pauseMs);
  } else if (scenario === "cooldown") {
    const seed = envInt("LLMTBG_CAP_BREACH_TOKENS", 5000);
    console.log("[STEP] Seed cap breach then verify cooldown blocks repeated call");
    await sendIngestEvent(ingestKey, provider, model, seed, "cooldown-breach-seed", env);
    await sleep(pauseMs);
  }

  let blocked: boolean;
  if (scenario === "cooldown") {
    const blockedFirst = await runProviderCall(provider, model, callMaxTokens, openai, anthropic, googleModel);
    const blockedSecond = await runProviderCall(provider, model, callMaxTokens, openai, anthropic, googleModel);
    blocked = blockedFirst && blockedSecond;
  } else {
    blocked = await runProviderCall(provider, model, callMaxTokens, openai, anthropic, googleModel);
  }
  await client.flush();
  const after = await providerCount();
  const providerCallsDelta = after - before;
  const usedMaxTokens = extractUsedMaxTokens(providerLastCall());
  const clampRecommended = lastClampRecommended;
  const clampApplied = lastClampApplied;

  console.log(`[RESULT] blocked=${blocked} provider_calls_delta=${providerCallsDelta}`);
  if (scenario === "near_cap") {
    console.log(`[CLAMP] recommended=${clampRecommended} applied=${clampApplied} used_max_tokens=${usedMaxTokens}`);
  }

  let incidentTypes = new Set<string>();
  if (projectId && authToken) {
    const incidents = await listOpenIncidents(projectId, provider, authToken);
    const counts = new Map<string, number>();
    const nearTypes = new Set<string>();
    for (const incident of incidents) counts.set(incident.type, (counts.get(incident.type) ?? 0) + 1);
    for (const incident of incidents) {
      if (incident.type === "near_cap" && typeof incident.evidence?.near_cap_type === "string" && incident.evidence.near_cap_type) {
        nearTypes.add(incident.evidence.near_cap_type);
      }
    }
    incidentTypes = new Set(incidents.map((incident) => incident.type));
    const compact = Array.from(counts.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${k}=${v}`)
      .join(", ");
    if (nearTypes.size > 0) {
      console.log(`[INCIDENTS] open=${incidents.length} types=${compact || "none"} near_cap_types=${Array.from(nearTypes).sort().join(",")}`);
    } else {
      console.log(`[INCIDENTS] open=${incidents.length} types=${compact || "none"}`);
    }
  } else {
    console.log("[INCIDENTS] skipped (set LLMTBG_PROJECT_ID and LLMTBG_AUTH_TOKEN)");
  }

  const decision = lastDecisionValue;
  const reason = lastDecisionReason;
  if (scenario === "allow") {
    assertLine("allow passed", !blocked && providerCallsDelta >= 1 && decision === "allow");
  } else if (scenario === "near_cap") {
    assertLine("near_cap warn triggered", !blocked && decision === "warn" && reason === "near_cap");
    const clampSuggested = typeof clampRecommended === "number" && clampRecommended > 0;
    const clampEnforced = clampSuggested && usedMaxTokens === clampRecommended && providerCallsDelta >= 1;
    assertLine("clamp applied / clamp suggested", clampSuggested || clampEnforced);
  } else if (scenario === "cap_breach") {
    assertLine("cap breach blocked", blocked && providerCallsDelta === 0 && incidentTypes.has("cap_breach"));
  } else if (scenario === "req_cap_breach") {
    assertLine("req_cap breach blocked", blocked && providerCallsDelta === 0 && incidentTypes.has("cap_breach"));
    assertLine("req_cap breach triggered block", blocked && providerCallsDelta === 0);
  } else if (scenario === "retry_storm") {
    assertLine("retry_storm warn triggered", !blocked && decision === "warn" && reason === "retry_storm");
  } else if (scenario === "loop_suspect") {
    assertLine("loop_suspect warn triggered", !blocked && decision === "warn" && reason === "loop_suspect");
  } else if (scenario === "token_explosion") {
    assertLine("token_explosion warn triggered", !blocked && decision === "warn" && (reason === "token_explosion" || reason === "near_cap"));
  } else if (scenario === "cooldown") {
    assertLine("cooldown active", blocked && providerCallsDelta === 0);
    assertLine("cooldown active - repeated call blocked", blocked && providerCallsDelta === 0);
  }

  await client.flush();
  console.log("[DEMO] sdk delivery stats:", client.getStats());
  client.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
