import { createClient, instrumentAnthropic, instrumentGoogle, instrumentOpenAI, RHEONICBlockedError } from "../../../sdk-node/dist/index.js";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DashboardSession } from "./dashboard_session.mjs";

function loadRheonicEnvFromDotenv() {
  const currentFile = fileURLToPath(import.meta.url);
  const repoRoot = resolve(dirname(currentFile), "../../..");
  const candidatePaths = [];
  if ((process.env.RHEONIC_ENV_FILE ?? "").trim()) {
    candidatePaths.push(process.env.RHEONIC_ENV_FILE.trim());
  }
  candidatePaths.push(resolve(repoRoot, ".env.staging.demo"));
  candidatePaths.push(resolve(repoRoot, ".env"));

  for (const dotenvPath of candidatePaths) {
    let content = "";
    try {
      content = readFileSync(dotenvPath, "utf8");
    } catch {
      continue;
    }
    for (const rawLine of content.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#") || !line.includes("=")) continue;
      const index = line.indexOf("=");
      const key = line.slice(0, index).trim();
      if (!key.startsWith("RHEONIC_")) continue;
      const value = line.slice(index + 1).trim().replace(/^['"]|['"]$/g, "");
      if (!(key in process.env)) {
        process.env[key] = value;
      }
    }
  }
}

loadRheonicEnvFromDotenv();

const backendBaseUrl = process.env.RHEONIC_BACKEND_URL ?? "http://localhost:8000";
const providerStubUrl = process.env.RHEONIC_PROVIDER_URL ?? "http://localhost:8099";
let lastProviderCall = null;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function envInt(name, fallback) {
  const raw = process.env[name];
  if (typeof raw !== "string" || raw.trim() === "") return fallback;
  const parsed = Number.parseInt(raw.trim(), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

async function providerCount() {
  const res = await fetch(`${providerStubUrl}/count`);
  if (!res.ok) throw new Error(`provider_stub_count_failed:${res.status}`);
  const payload = await res.json();
  return Number(payload.count ?? 0);
}

async function resetProvider() {
  const res = await fetch(`${providerStubUrl}/reset`, { method: "POST" });
  if (!res.ok) throw new Error(`provider_stub_reset_failed:${res.status}`);
}

async function callProviderStub(payload) {
  if (payload && typeof payload === "object") {
    lastProviderCall = payload;
  }
  const res = await fetch(`${providerStubUrl}/call`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`provider_stub_call_failed:${res.status}`);
}

function providerLastCall() {
  return lastProviderCall;
}

function extractUsedMaxTokens(payload) {
  if (!payload) return null;
  const value = payload.max_tokens;
  if (typeof value === "number" && Number.isFinite(value)) return Math.floor(value);
  return null;
}

function assertLine(label, passed) {
  console.log(passed ? `[ASSERT] ${label}` : `[ASSERT] ${label} (FAILED)`);
}

async function sendIngestEvent(ingestKey, provider, model, totalTokens, feature, environment, options) {
  const status = options?.status ?? "ok";
  const httpStatus = options?.httpStatus ?? 200;
  const payload = {
    ts: new Date().toISOString(),
    provider,
    model,
    environment,
    latency_ms: 120,
    http_status: httpStatus,
    ...(options?.errorType ? { error_type: options.errorType } : {}),
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

async function listOpenIncidents(projectId, provider, dashboardSession) {
  if (!projectId || !dashboardSession) return [];
  const params = new URLSearchParams({ project_id: projectId, status: "open", provider });
  try {
    return await dashboardSession.request(`/api/v1/incidents?${params.toString()}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message.includes("(401)") || message.includes("(403)")) {
      console.log("[INCIDENTS] skipped (dashboard cookie session is not authenticated)");
      return [];
    }
    throw error;
  }
}

async function getProjectReqCap(projectId, dashboardSession) {
  if (!projectId || !dashboardSession) return null;
  let payload;
  try {
    payload = await dashboardSession.request(`/api/v1/projects/${projectId}/protect`);
  } catch {
    return null;
  }
  const value = payload.protect_max_req_per_min;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 1) return null;
  return Math.floor(value);
}

async function runProviderCall(provider, model, maxTokens, openai, anthropic, googleModel) {
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
    if (error instanceof RHEONICBlockedError) return true;
    throw error;
  }
}

async function main() {
  const ingestKey = process.env.RHEONIC_INGEST_KEY;
  if (!ingestKey) {
    console.error("RHEONIC_INGEST_KEY is required.");
    process.exit(1);
  }

  const provider = (process.env.RHEONIC_PROVIDER ?? "").trim().toLowerCase();
  if (!provider || !["openai", "anthropic", "google"].includes(provider)) {
    console.error("RHEONIC_PROVIDER is required (openai | anthropic | google).");
    process.exit(1);
  }

  const model = (process.env.RHEONIC_MODEL ?? "").trim();
  if (!model) {
    console.error(`RHEONIC_MODEL is required for provider ${provider}.`);
    process.exit(1);
  }

  const scenario = (process.env.RHEONIC_SCENARIO ?? "allow").toLowerCase();
  const pauseMs = envInt("RHEONIC_STEP_SLEEP_MS", 200);
  const protectDecisionTimeoutMs = envInt("RHEONIC_PROTECT_DECISION_TIMEOUT_MS", 250);
  const env = (process.env.RHEONIC_ENVIRONMENT ?? "").trim() || `protect-${Date.now()}`;
  const projectId = process.env.RHEONIC_PROJECT_ID ?? "";
  const authEmail = (process.env.RHEONIC_AUTH_EMAIL ?? "").trim().toLowerCase();
  const authPassword = process.env.RHEONIC_AUTH_PASSWORD ?? "";
  let dashboardSession = null;

  if (projectId && authEmail && authPassword) {
    dashboardSession = new DashboardSession(backendBaseUrl);
    try {
      await dashboardSession.login(authEmail, authPassword);
      console.log("[INCIDENTS] dashboard cookie session ready");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.log(`[INCIDENTS] dashboard cookie session unavailable (${message})`);
      dashboardSession = null;
    }
  }

  await resetProvider();
  const before = await providerCount();

  const client = createClient({
    baseUrl: backendBaseUrl,
    ingestKey,
    environment: env,
    debug: process.env.RHEONIC_DEBUG === "1" || process.env.RHEONIC_DEBUG === "true",
    flushIntervalMs: 60_000,
  });
  await client.warmConnections();
  client.protectEngine.decisionTimeoutMs = protectDecisionTimeoutMs;

  let lastDecisionValue = "";
  let lastDecisionReason = "";
  let lastClampRecommended = null;
  let lastClampApplied = null;
  let lastDecisionPayload = null;
  const originalEvaluateProtectDecision = client.evaluateProtectDecision.bind(client);
  client.evaluateProtectDecision = async (context) => {
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
    lastDecisionPayload = decision;
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
        create: async (payload) => {
          await callProviderStub(payload);
          return { model: payload.model, usage: { total_tokens: 10 } };
        },
      },
    },
  };
  const anthropic = {
    messages: {
      create: async (payload) => {
        await callProviderStub(payload);
        return { model: payload.model, usage: { input_tokens: 6, output_tokens: 4 } };
      },
    },
  };
  const googleModel = {
    model,
    generateContent: async (payload) => {
      const requestPayload = typeof payload === "string" ? { prompt: payload } : payload;
      await callProviderStub(requestPayload);
      return { response: { usageMetadata: { totalTokenCount: 10 } } };
    },
  };

  const decisionFeature = scenario === "loop_suspect" ? "loop-fixed-signature" : "manual-protect-demo";
  instrumentOpenAI(openai, { client, feature: decisionFeature, environment: env });
  instrumentAnthropic(anthropic, { client, feature: decisionFeature, environment: env });
  instrumentGoogle(googleModel, { client, feature: decisionFeature, environment: env });

  console.log(`[DEMO] provider=${provider} model=${model} scenario=${scenario}`);
  console.log(`[DEMO] environment=${env}`);
  console.log(`[DEMO] protect_decision_timeout_ms=${protectDecisionTimeoutMs}`);
  console.log(`[DEMO] decision_feature=${decisionFeature}`);
  const maxTokens = envInt("RHEONIC_MAX_TOKENS", 128);
  let callMaxTokens = maxTokens;
  console.log(`[DEMO] max_tokens(before call)=${maxTokens}`);

  if (scenario === "near_cap") {
    const seed = Number(process.env.RHEONIC_NEAR_CAP_SEED_TOKENS ?? 1600);
    console.log("[STEP] Seed near-cap traffic then expect warn");
    await sendIngestEvent(ingestKey, provider, model, seed, "near-cap-seed", env);
    await sleep(pauseMs);
  } else if (scenario === "cap_breach") {
    const seed = Number(process.env.RHEONIC_CAP_BREACH_TOKENS ?? 5000);
    console.log("[STEP] Seed cap breach then expect block");
    await sendIngestEvent(ingestKey, provider, model, seed, "cap-breach-seed", env);
    await sleep(pauseMs);
  } else if (scenario === "req_cap_breach") {
    let count = envInt("RHEONIC_REQ_CAP_BREACH_COUNT", 6);
    const reqTokens = envInt("RHEONIC_CAP_BREACH_REQ_TOKENS", 1);
    const reqCap = await getProjectReqCap(projectId, dashboardSession);
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
    const count = envInt("RHEONIC_RETRY_STORM_COUNT", 6);
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
    const count = envInt("RHEONIC_LOOP_COUNT", 7);
    console.log("[STEP] Seed loop suspect then expect warn");
    for (let i = 0; i < count; i += 1) {
      await sendIngestEvent(ingestKey, provider, model, 60, "loop-fixed-signature", env);
      await sleep(pauseMs);
    }
  } else if (scenario === "token_explosion") {
    const seed = envInt("RHEONIC_TOKEN_EXPLOSION_TOKENS", 9000);
    console.log("[STEP] Seed token explosion then expect warn");
    await sendIngestEvent(ingestKey, provider, model, seed, "token-explosion-seed", env);
    callMaxTokens = Math.max(maxTokens, seed);
    console.log(`[STEP] token_explosion call max_tokens=${callMaxTokens}`);
    await sleep(pauseMs);
  } else if (scenario === "cooldown") {
    const seed = envInt("RHEONIC_CAP_BREACH_TOKENS", 5000);
    console.log("[STEP] Seed cap breach then verify cooldown blocks repeated call");
    await sendIngestEvent(ingestKey, provider, model, seed, "cooldown-breach-seed", env);
    await sleep(pauseMs);
  }

  let blocked;
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

  console.log(`[RESULT] blocked=${blocked} provider_calls_delta=${providerCallsDelta}`);
  if (scenario === "near_cap") {
    console.log(`[CLAMP] recommended=${lastClampRecommended} applied=${lastClampApplied} used_max_tokens=${usedMaxTokens}`);
  }

  let incidentTypes = new Set();
  if (projectId && dashboardSession) {
    const incidents = await listOpenIncidents(projectId, provider, dashboardSession);
    const counts = new Map();
    const nearTypes = new Set();
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
    console.log("[INCIDENTS] skipped (set RHEONIC_PROJECT_ID, RHEONIC_AUTH_EMAIL, and RHEONIC_AUTH_PASSWORD)");
  }

  const decision = lastDecisionValue;
  const reason = lastDecisionReason;
  if (scenario === "allow") {
    assertLine("allow passed", !blocked && providerCallsDelta >= 1 && decision === "allow");
  } else if (scenario === "near_cap") {
    assertLine("near_cap warn triggered", !blocked && decision === "warn" && reason === "near_cap");
    const clampSuggested = typeof lastClampRecommended === "number" && lastClampRecommended > 0;
    const clampEnforced = clampSuggested && usedMaxTokens === lastClampRecommended && providerCallsDelta >= 1;
    assertLine("clamp suggested", clampSuggested);
    if (lastDecisionPayload?.apply_clamp_enabled === true) {
      assertLine("clamp applied", Boolean(lastClampApplied) && clampEnforced);
    } else {
      assertLine("clamp not applied", !lastClampApplied && !clampEnforced);
    }
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
