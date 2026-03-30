import { createClient, instrumentAnthropic, instrumentGoogle, instrumentOpenAI, RHEONICBlockedError } from "../../../sdk-node/dist/index.js";
import { DashboardSession } from "./dashboard_session.mjs";

const backendBaseUrl = process.env.RHEONIC_BACKEND_URL ?? "http://localhost:8000";
const providerStubUrl = process.env.RHEONIC_PROVIDER_URL ?? "http://localhost:8099";
let lastProviderCall = null;
let localProviderCallCount = 0;
let providerStubAvailable = null;

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
  if (providerStubAvailable !== false) {
    const res = await providerStubRequest("/count");
    if (res) {
      const payload = await res.json();
      return Number(payload.count ?? 0);
    }
  }
  return localProviderCallCount;
}

async function resetProvider() {
  lastProviderCall = null;
  localProviderCallCount = 0;
  await providerStubRequest("/reset", { method: "POST" });
}

async function providerStubRequest(path, init) {
  try {
    const res = await fetch(`${providerStubUrl}${path}`, init);
    if (!res.ok) throw new Error(`provider_stub_request_failed:${res.status}`);
    providerStubAvailable = true;
    return res;
  } catch {
    if (providerStubAvailable !== false) {
      console.log(`[PROVIDER] stub unavailable at ${providerStubUrl}; using in-process call tracking`);
    }
    providerStubAvailable = false;
    return null;
  }
}

async function callProviderStub(payload) {
  if (payload && typeof payload === "object") {
    lastProviderCall = payload;
  }
  localProviderCallCount += 1;
  if (providerStubAvailable !== false) {
    await providerStubRequest("/call", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }
}

function providerLastCall() {
  return lastProviderCall;
}

function extractUsedMaxTokens(payload) {
  if (!payload) return null;
  const value = payload.max_tokens;
  if (typeof value === "number" && Number.isFinite(value)) return Math.floor(value);
  const generationConfig = payload.generation_config;
  if (generationConfig && typeof generationConfig === "object") {
    const maxOutput = generationConfig.max_output_tokens;
    if (typeof maxOutput === "number" && Number.isFinite(maxOutput)) return Math.floor(maxOutput);
  }
  return null;
}

function resolveSimulatedTotalTokens(payload, fallback = 10) {
  const maxTokens = extractUsedMaxTokens(payload);
  const promptTokens = estimatePromptTokens(payload);
  return Math.max(typeof maxTokens === "number" && maxTokens > 0 ? maxTokens : 0, promptTokens, fallback);
}

function collectPromptFragments(value, parts) {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed) parts.push(trimmed);
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      collectPromptFragments(item, parts);
    }
    return;
  }
  if (!value || typeof value !== "object") return;
  if (typeof value.text === "string") {
    collectPromptFragments(value.text, parts);
  }
  if ("content" in value) {
    collectPromptFragments(value.content, parts);
  }
}

function estimatePromptTokens(payload) {
  if (!payload || typeof payload !== "object") return 0;
  const parts = [];
  if (typeof payload.prompt === "string") {
    collectPromptFragments(payload.prompt, parts);
  }
  if (Array.isArray(payload.messages)) {
    for (const message of payload.messages) {
      collectPromptFragments(message?.content, parts);
    }
  }
  const text = parts.join(" ").trim();
  if (!text) return 0;
  const wordEstimate = text.split(/\s+/).length;
  const charEstimate = Math.ceil(text.length / 4);
  return Math.max(wordEstimate, charEstimate);
}

function printConfigHint() {
  const targetHint = (process.env.RHEONIC_DEMO_TARGET_HINT ?? "").trim() || "protect-prod-node";
  console.log(`Run: make ${targetHint} RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=tok_cap_breach`);
  console.log("Optional exact provider-call visibility: python3 tests/e2e/provider_stub.py");
}

function assertLine(label, passed) {
  console.log(passed ? `[ASSERT] ${label}` : `[ASSERT] ${label} (FAILED)`);
}

function assertDelivery(client, expectedMinSent = 0) {
  const stats = client.getStats();
  console.log("[DEMO] sdk delivery stats:", stats);
  const sent = Number(stats.sent ?? 0);
  const failed = Number(stats.failed ?? 0);
  const queued = Number(stats.queued ?? 0);
  if (sent < expectedMinSent || failed > 0 || queued > 0) {
    throw new Error(`protect demo did not fully deliver SDK events (sent=${sent}, failed=${failed}, queued=${queued})`);
  }
}

async function sendIngestEvent(ingestKey, provider, model, totalTokens, feature, environment, options) {
  const endpointByProvider = {
    openai: "/chat/completions",
    anthropic: "/v1/messages",
    google: "/v1beta/models/generateContent",
  };
  const endpoint = endpointByProvider[provider] ?? "/chat/completions";
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
    request: {
      endpoint,
      feature,
      input_tokens: 1,
      ...(typeof options?.tokenExplosionTokens === "number"
        ? { token_explosion_tokens: options.tokenExplosionTokens }
        : {}),
    },
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

async function assertProjectIsInProtectMode(projectId, dashboardSession) {
  if (!projectId || !dashboardSession) return;
  const payload = await dashboardSession.request(`/api/v1/projects/${projectId}/protect`);
  if (!payload?.protect_enabled) {
    throw new Error(
      "Protect demo requires project mode Protect. Current project mode is Observe, " +
        "so protect decision counters will stay at zero even though usage metrics still increment."
    );
  }
}

async function runProviderCall(provider, model, maxTokens, openai, anthropic, googleModel) {
  return await runProviderCallWithPrompt(provider, model, maxTokens, "protect demo request", openai, anthropic, googleModel);
}

async function runProviderCallWithPrompt(provider, model, maxTokens, promptText, openai, anthropic, googleModel) {
  try {
    if (provider === "anthropic") {
      await anthropic.messages.create({
        model,
        messages: [{ role: "user", content: promptText }],
        max_tokens: maxTokens,
      });
    } else if (provider === "google") {
      await googleModel.generateContent({
        prompt: promptText,
        generation_config: { max_output_tokens: maxTokens },
      });
    } else {
      await openai.chat.completions.create({
        model,
        messages: [{ role: "user", content: promptText }],
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
    printConfigHint();
    process.exit(1);
  }

  const provider = (process.env.RHEONIC_PROVIDER ?? "").trim().toLowerCase();
  if (!provider || !["openai", "anthropic", "google"].includes(provider)) {
    console.error("RHEONIC_PROVIDER is required (openai | anthropic | google).");
    printConfigHint();
    process.exit(1);
  }

  const model = (process.env.RHEONIC_MODEL ?? "").trim();
  if (!model) {
    console.error(`RHEONIC_MODEL is required for provider ${provider}.`);
    printConfigHint();
    process.exit(1);
  }

  const scenario = (process.env.RHEONIC_SCENARIO ?? "allow").toLowerCase();
  const pauseMs = envInt("RHEONIC_STEP_SLEEP_MS", 200);
  const protectDecisionTimeoutMs = envInt("RHEONIC_PROTECT_DECISION_TIMEOUT_MS", 160);
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
  await assertProjectIsInProtectMode(projectId, dashboardSession);

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
  let promptText = "protect demo request";
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
          return { model: payload.model, usage: { total_tokens: resolveSimulatedTotalTokens(payload) } };
        },
      },
    },
  };
  const anthropic = {
    messages: {
      create: async (payload) => {
        await callProviderStub(payload);
        const totalTokens = resolveSimulatedTotalTokens(payload);
        return { model: payload.model, usage: { input_tokens: 1, output_tokens: Math.max(totalTokens - 1, 1) } };
      },
    },
  };
  const googleModel = {
    model,
    generateContent: async (payload) => {
      const requestPayload = typeof payload === "string" ? { prompt: payload } : payload;
      await callProviderStub(requestPayload);
      return { response: { usageMetadata: { totalTokenCount: resolveSimulatedTotalTokens(requestPayload) } } };
    },
  };

  const decisionFeature =
    scenario === "loop_suspect"
      ? "loop-fixed-signature"
      : scenario === "token_explosion"
        ? "token-explosion-growth"
        : "manual-protect-demo";
  const endpointByProvider = {
    openai: "/chat/completions",
    anthropic: "/v1/messages",
    google: "/v1beta/models/generateContent",
  };
  const decisionEndpoint = endpointByProvider[provider] ?? "/chat/completions";
  instrumentOpenAI(openai, { client, feature: decisionFeature, environment: env, endpoint: decisionEndpoint });
  instrumentAnthropic(anthropic, { client, feature: decisionFeature, environment: env, endpoint: decisionEndpoint });
  instrumentGoogle(googleModel, { client, feature: decisionFeature, environment: env, endpoint: decisionEndpoint });

  console.log(`[DEMO] provider=${provider} model=${model} scenario=${scenario}`);
  console.log(`[DEMO] environment=${env}`);
  console.log(`[DEMO] protect_decision_timeout_ms=${protectDecisionTimeoutMs}`);
  console.log(`[DEMO] decision_feature=${decisionFeature}`);
  const maxTokens = envInt("RHEONIC_MAX_TOKENS", 128);
  let callMaxTokens = maxTokens;
  console.log(`[DEMO] max_tokens(before call)=${maxTokens}`);

  if (scenario === "clamp") {
    const seed = Number(process.env.RHEONIC_CLAMP_SEED_TOKENS ?? 1600);
    console.log("[STEP] Seed clamp traffic then expect clamp");
    await sendIngestEvent(ingestKey, provider, model, seed, "clamp-seed", env);
    await sleep(pauseMs);
  } else if (scenario === "tok_cap_breach") {
    const seed = Number(process.env.RHEONIC_TOK_CAP_BREACH_TOKENS ?? 5000);
    console.log("[STEP] Seed token-cap breach then expect block");
    await sendIngestEvent(ingestKey, provider, model, seed, "tok-cap-breach-seed", env);
    callMaxTokens = Math.max(maxTokens, seed);
    console.log(`[STEP] tok_cap_breach call max_tokens=${callMaxTokens}`);
    await sleep(pauseMs);
  } else if (scenario === "req_cap_breach") {
    let count = envInt("RHEONIC_REQ_CAP_BREACH_COUNT", 6);
    const reqTokens = envInt("RHEONIC_REQ_CAP_BREACH_TOKENS", 1);
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
    const count = envInt("RHEONIC_RETRY_STORM_COUNT", 5);
    console.log("[STEP] Seed failed attempts for retry storm then expect incident");
    for (let i = 0; i < count; i += 1) {
      await sendIngestEvent(ingestKey, provider, model, 50, `retry-${i + 1}`, env, {
        status: "error",
        httpStatus: 500,
        errorType: "provider_5xx",
      });
      await sleep(pauseMs);
    }
  } else if (scenario === "loop_suspect") {
    const count = envInt("RHEONIC_LOOP_COUNT", 6);
    console.log("[STEP] Seed a rapid repeated sequence for loop suspect then expect incident");
    for (let i = 0; i < count; i += 1) {
      await sendIngestEvent(ingestKey, provider, model, 60, "loop-fixed-signature", env);
      await sleep(pauseMs);
    }
  } else if (scenario === "token_explosion") {
    const peak = Math.max(envInt("RHEONIC_TOKEN_EXPLOSION_TOKENS", 5500), 5500);
    const stepOne = 1900;
    const stepTwoMin = Math.ceil(stepOne * 1.7);
    const stepTwoMax = Math.floor(peak / 1.7);
    const stepTwo = Math.max(stepTwoMin, stepTwoMax);
    const growthSteps = [stepOne, stepTwo];
    console.log(`[STEP] Seed token explosion growth history then expect incident (history=${growthSteps.join(" -> ")}, live=${peak})`);
    for (const growthValue of growthSteps) {
      await sendIngestEvent(ingestKey, provider, model, growthValue, "token-explosion-growth", env, {
        tokenExplosionTokens: growthValue,
      });
      await sleep(pauseMs);
    }
    promptText = Array.from({ length: peak }, () => "growth").join(" ");
    callMaxTokens = maxTokens;
    console.log(`[STEP] token_explosion live prompt targets request-context growth to ~${peak} tokens`);
    await sleep(pauseMs);
  } else if (scenario === "cooldown") {
    const seed = envInt("RHEONIC_TOK_CAP_BREACH_TOKENS", 5000);
    console.log("[STEP] Seed token-cap breach then verify cooldown blocks repeated call");
    await sendIngestEvent(ingestKey, provider, model, seed, "cooldown-block-seed", env);
    callMaxTokens = Math.max(maxTokens, seed);
    console.log(`[STEP] cooldown call max_tokens=${callMaxTokens}`);
    await sleep(pauseMs);
  }

  let blocked;
  if (scenario === "cooldown") {
    const blockedFirst = await runProviderCallWithPrompt(
      provider,
      model,
      callMaxTokens,
      promptText,
      openai,
      anthropic,
      googleModel,
    );
    const blockedSecond = await runProviderCallWithPrompt(
      provider,
      model,
      callMaxTokens,
      promptText,
      openai,
      anthropic,
      googleModel,
    );
    blocked = blockedFirst && blockedSecond;
  } else {
    blocked = await runProviderCallWithPrompt(provider, model, callMaxTokens, promptText, openai, anthropic, googleModel);
  }
  await client.flush();
  await sleep(pauseMs);
  const after = await providerCount();
  const providerCallsDelta = after - before;
  const usedMaxTokens = extractUsedMaxTokens(providerLastCall());
  lastClampApplied = Boolean(
    typeof lastClampRecommended === "number" &&
      typeof maxTokens === "number" &&
      lastClampRecommended < maxTokens &&
      usedMaxTokens === lastClampRecommended &&
      providerCallsDelta >= 1
  );

  console.log(`[RESULT] blocked=${blocked} provider_calls_delta=${providerCallsDelta}`);
  if (scenario === "clamp") {
    console.log(`[CLAMP] recommended=${lastClampRecommended} applied=${lastClampApplied} used_max_tokens=${usedMaxTokens}`);
  }

  let incidentTypes = new Set();
  if (projectId && dashboardSession) {
    const incidents = await listOpenIncidents(projectId, provider, dashboardSession);
    const counts = new Map();
    for (const incident of incidents) counts.set(incident.type, (counts.get(incident.type) ?? 0) + 1);
    incidentTypes = new Set(incidents.map((incident) => incident.type));
    const compact = Array.from(counts.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${k}=${v}`)
      .join(", ");
    console.log(`[INCIDENTS] open=${incidents.length} types=${compact || "none"}`);
  } else {
    console.log("[INCIDENTS] skipped (set RHEONIC_PROJECT_ID, RHEONIC_AUTH_EMAIL, and RHEONIC_AUTH_PASSWORD)");
  }

  const decision = lastDecisionValue;
  const reason = lastDecisionReason;
  if (scenario === "allow") {
    assertLine("allow passed", !blocked && providerCallsDelta >= 1 && decision === "allow");
  } else if (scenario === "clamp") {
    assertLine("clamp triggered", !blocked && decision === "clamp" && reason === "token_clamp");
    const clampSuggested = typeof lastClampRecommended === "number" && lastClampRecommended > 0;
    const clampShouldApply = clampSuggested && typeof maxTokens === "number" && lastClampRecommended < maxTokens;
    const clampEnforced = clampSuggested && usedMaxTokens === lastClampRecommended && providerCallsDelta >= 1;
    assertLine("clamp suggested", clampSuggested);
    if (lastDecisionPayload?.apply_clamp_enabled === true && clampShouldApply) {
      assertLine("clamp applied", clampEnforced);
    } else {
      assertLine("clamp not applied", !lastClampApplied && !clampEnforced);
    }
  } else if (scenario === "tok_cap_breach") {
    assertLine("token cap breach blocked", blocked && providerCallsDelta === 0 && reason === "tok_cap_breach");
    assertLine("block incident opened", incidentTypes.has("block"));
  } else if (scenario === "req_cap_breach") {
    assertLine("req_cap breach blocked", blocked && providerCallsDelta === 0 && reason === "req_cap_breach");
    assertLine("block incident opened", incidentTypes.has("block"));
    assertLine("req_cap breach triggered block", blocked && providerCallsDelta === 0);
  } else if (scenario === "retry_storm") {
    assertLine(
      "retry_storm stayed allowed at preflight",
      !blocked && decision === "allow",
    );
    assertLine("retry_storm incident opened", incidentTypes.has("retry_storm"));
  } else if (scenario === "loop_suspect") {
    assertLine(
      "loop_suspect stayed allowed at preflight",
      !blocked && decision === "allow",
    );
    assertLine("loop_suspect incident opened", incidentTypes.has("loop_suspect"));
  } else if (scenario === "token_explosion") {
    assertLine("token_explosion stayed allowed at preflight", !blocked && decision === "allow");
    assertLine("token_explosion incident opened", incidentTypes.has("token_explosion"));
  } else if (scenario === "cooldown") {
    assertLine("cooldown active", blocked && providerCallsDelta === 0);
    assertLine("cooldown active - repeated call blocked", blocked && providerCallsDelta === 0);
  }

  await client.flush();
  await sleep(pauseMs);
  assertDelivery(client, providerCallsDelta >= 1 ? 1 : 0);
  client.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
