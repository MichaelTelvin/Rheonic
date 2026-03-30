import { buildEvent, createClient } from "../../../sdk-node/dist/index.js";
import { DashboardSession } from "./dashboard_session.mjs";

const verbose = ["1", "true", "yes"].includes((process.env.RHEONIC_VERBOSE ?? "").trim().toLowerCase());

function log(message) {
  console.log(message);
}

function logVerbose(message) {
  if (verbose) {
    console.log(message);
  }
}

function assertDelivery(client, expectedMinSent = 1) {
  const stats = client.getStats();
  log(`[DEMO] sdk delivery stats: ${JSON.stringify(stats)}`);
  const sent = Number(stats.sent ?? 0);
  const failed = Number(stats.failed ?? 0);
  const queued = Number(stats.queued ?? 0);
  if (sent < expectedMinSent || failed > 0 || queued > 0) {
    throw new Error(
      `observe demo did not fully deliver events (sent=${sent}, failed=${failed}, queued=${queued})`,
    );
  }
}

function printConfigHint() {
  const targetHint = (process.env.RHEONIC_DEMO_TARGET_HINT ?? "").trim() || "demo-prod-node";
  console.log(`  Run: make ${targetHint} RHEONIC_PROVIDER=google RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=req_cap_breach`);
}

function printUsageExamples() {
  console.log("Example:");
  console.log("  RHEONIC_PROVIDER=openai");
  console.log("  RHEONIC_MODEL=gpt-4o-mini");
  console.log("  RHEONIC_DEMO_CASE=steady|near_cap|retry_storm|loop_suspect|token_explosion|cap_breach|req_cap_breach|all");
  console.log("  RHEONIC_STEP_SLEEP_MS=200");
  console.log("  RHEONIC_RETRY_STORM_COUNT=5");
  console.log("  RHEONIC_LOOP_COUNT=6");
  console.log("  RHEONIC_TOKEN_EXPLOSION_TOKENS=10000");
  console.log("  RHEONIC_CAP_BREACH_TOKENS=4000");
  console.log("  RHEONIC_REQ_CAP_BREACH_COUNT=6");
  console.log("  RHEONIC_CAP_BREACH_REQ_TOKENS=1");
  console.log("  RHEONIC_NEAR_CAP_TOKENS=3200");
  console.log("  Optional snapshot/incident summary:");
  console.log("  RHEONIC_AUTH_EMAIL=<email> RHEONIC_AUTH_PASSWORD=<password> RHEONIC_PROJECT_ID=<project_id>");
  printConfigHint();
}
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchRealtimeSnapshot(dashboardSession, projectId, provider, phase) {
  if (!dashboardSession || !projectId) {
    logVerbose(`[SNAPSHOT] ${phase}: (snapshot skipped: no dashboard session/project id)`);
    return;
  }
  const params = new URLSearchParams({ project_id: projectId });
  if (provider !== "all") params.set("provider", provider);
  try {
    const payload = await dashboardSession.request(`/api/v1/metrics/realtime?${params.toString()}`);
    logVerbose(`[SNAPSHOT] ${phase}: req60=${payload.requests_60s} tok60=${payload.tokens_60s}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logVerbose(`[SNAPSHOT] ${phase}: unavailable (${message})`);
    return;
  }
}

async function fetchIncidentSummary(dashboardSession, projectId, provider) {
  if (!dashboardSession || !projectId) {
    logVerbose("[OBSERVE] incidents: (skipped: no dashboard session/project id)");
    return;
  }
  const params = new URLSearchParams({ project_id: projectId, status: "open" });
  if (provider !== "all") params.set("provider", provider);
  let incidents;
  try {
    incidents = await dashboardSession.request(`/api/v1/incidents?${params.toString()}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logVerbose(`[OBSERVE] incidents summary unavailable (${message})`);
    return;
  }
  const counts = new Map();
  for (const incident of incidents) {
    const t = (incident.type ?? "unknown").toString();
    counts.set(t, (counts.get(t) ?? 0) + 1);
  }
  const compact = Array.from(counts.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`)
    .join(", ");
  logVerbose(`[OBSERVE] incidents open=${incidents.length} types=${compact || "none"}`);
}

async function printPhase(dashboardSession, phase, projectId, provider) {
  await fetchRealtimeSnapshot(dashboardSession, projectId, provider, phase);
  await fetchIncidentSummary(dashboardSession, projectId, provider);
}

async function sendEvent(client, provider, model, endpoint, totalTokens, feature, options) {
  const event = buildEvent({
    provider,
    model,
    environment: client.environment,
    request: {
      endpoint,
      feature,
      ...(typeof options?.tokenExplosionTokens === "number"
        ? { token_explosion_tokens: options.tokenExplosionTokens }
        : {}),
    },
    response: {
      latency_ms: 120,
      total_tokens: totalTokens,
    },
  });
  event.status = options?.status ?? "ok";
  event.http_status = options?.httpStatus ?? 200;
  if (options?.errorType) {
    event.error_type = options.errorType;
  }
  await client.captureEvent(event);
}

async function runDemo() {
  const backendBaseUrl = (process.env.RHEONIC_BACKEND_URL ?? "http://localhost:8000").replace(/\/$/, "");
  const ingestKey = process.env.RHEONIC_INGEST_KEY;
  if (!ingestKey) {
    console.error("RHEONIC_INGEST_KEY is required. Create a key in dashboard Keys page.");
    printUsageExamples();
    process.exitCode = 1;
    return;
  }

  const provider = (process.env.RHEONIC_PROVIDER ?? "").trim().toLowerCase();
  if (!provider || !["openai", "anthropic", "google"].includes(provider)) {
    console.error("RHEONIC_PROVIDER is required (openai | anthropic | google).");
    printUsageExamples();
    process.exitCode = 1;
    return;
  }

  const model = (process.env.RHEONIC_MODEL ?? "").trim();
  if (!model) {
    console.error(`RHEONIC_MODEL is required for provider ${provider}.`);
    printUsageExamples();
    process.exitCode = 1;
    return;
  }

  const endpointByProvider = {
    openai: "/chat/completions",
    anthropic: "/v1/messages",
    google: "/v1beta/models/generateContent",
  };
  const endpoint = endpointByProvider[provider] ?? "/chat/completions";
  const demoCase = (process.env.RHEONIC_DEMO_CASE ?? "steady").toLowerCase();
  const stepSleepMs = Number(process.env.RHEONIC_STEP_SLEEP_MS ?? 200);
  const retryStormCount = Number(process.env.RHEONIC_RETRY_STORM_COUNT ?? 5);
  const loopCount = Number(process.env.RHEONIC_LOOP_COUNT ?? 6);
  const tokenExplosionTokens = Number(process.env.RHEONIC_TOKEN_EXPLOSION_TOKENS ?? 10000);
  const capBreachTokens = Number(process.env.RHEONIC_CAP_BREACH_TOKENS ?? 4000);
  const capBreachReqCount = Number(process.env.RHEONIC_REQ_CAP_BREACH_COUNT ?? 6);
  const capBreachReqTokens = Number(process.env.RHEONIC_CAP_BREACH_REQ_TOKENS ?? 1);
  const nearCapTokens = Number(process.env.RHEONIC_NEAR_CAP_TOKENS ?? 3200);
  const projectId = process.env.RHEONIC_PROJECT_ID ?? "";
  const authEmail = (process.env.RHEONIC_AUTH_EMAIL ?? "").trim().toLowerCase();
  const authPassword = process.env.RHEONIC_AUTH_PASSWORD ?? "";
  const environment = (process.env.RHEONIC_ENVIRONMENT ?? "").trim() || `demo-${Date.now()}`;
  let dashboardSession = null;

  if (projectId && authEmail && authPassword) {
    dashboardSession = new DashboardSession(backendBaseUrl);
    try {
      await dashboardSession.login(authEmail, authPassword);
      logVerbose("[OBSERVE] dashboard cookie session ready");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      logVerbose(`[OBSERVE] dashboard cookie session unavailable (${message})`);
      dashboardSession = null;
    }
  }

  const client = createClient({
    ingestKey,
    environment,
    debug: process.env.RHEONIC_DEBUG === "1" || process.env.RHEONIC_DEBUG === "true",
  });

  log(`[DEMO] observe ${demoCase} provider=${provider} model=${model} environment=${environment}`);
  logVerbose(
    `[DEMO] params retry_storm_count=${retryStormCount} loop_count=${loopCount} token_explosion_tokens=${tokenExplosionTokens} cap_breach_tokens=${capBreachTokens} cap_breach_req_count=${capBreachReqCount} cap_breach_req_tokens=${capBreachReqTokens} near_cap_tokens=${nearCapTokens} step_sleep_ms=${stepSleepMs}`,
  );

  const runSteady = async () => {
    logVerbose("\n[STEP] Steady traffic / no anomaly");
    await sendEvent(client, provider, model, endpoint, 42, "steady-1");
    await client.flush();
    await printPhase(dashboardSession, "steady", projectId, provider);
  };

  const runRetryStorm = async () => {
    logVerbose("\n[STEP] Retry storm from failed attempts");
    for (let i = 0; i < retryStormCount; i += 1) {
      await sendEvent(client, provider, model, endpoint, 50, `retry-${i + 1}`, {
        status: "error",
        httpStatus: 500,
        errorType: "provider_5xx",
      });
      await sleep(stepSleepMs);
    }
    await client.flush();
    await printPhase(dashboardSession, "retry_storm", projectId, provider);
  };

  const runNearCap = async () => {
    logVerbose("\n[STEP] Near-cap logging (observe)");
    logVerbose("[STEP] Requires project token/request cap configured in Settings page.");
    await sendEvent(client, provider, model, endpoint, nearCapTokens, "near-cap");
    await client.flush();
    await printPhase(dashboardSession, "near_cap", projectId, provider);
  };

  const runLoopSuspect = async () => {
    logVerbose("\n[STEP] Loop suspect from a rapid repeated sequence");
    for (let i = 0; i < loopCount; i += 1) {
      await sendEvent(client, provider, model, endpoint, 60, "loop-fixed-signature");
      await sleep(stepSleepMs);
    }
    await client.flush();
    await printPhase(dashboardSession, "loop_suspect", projectId, provider);
  };

  const runTokenExplosion = async () => {
    logVerbose("\n[STEP] Token explosion from repeated request-context growth");
    await sendEvent(client, provider, model, endpoint, tokenExplosionTokens, "token-explosion", {
      tokenExplosionTokens,
    });
    await client.flush();
    await printPhase(dashboardSession, "token_explosion", projectId, provider);
  };

  const runCapBreach = async () => {
    logVerbose("\n[STEP] Cap breach logging (observe)");
    logVerbose("[STEP] Requires project caps configured in Mode page (max requests/tokens per minute).");
    await sendEvent(client, provider, model, endpoint, capBreachTokens, "cap-breach");
    await client.flush();
    await printPhase(dashboardSession, "cap_breach", projectId, provider);
  };

  const runReqCapBreach = async () => {
    logVerbose("\n[STEP] Request cap breach logging (observe)");
    logVerbose("[STEP] Requires project request cap configured in Mode page (max requests per minute).");
    for (let i = 0; i < capBreachReqCount; i += 1) {
      await sendEvent(client, provider, model, endpoint, capBreachReqTokens, `req-cap-breach-${i + 1}`, {
        status: "ok",
        httpStatus: 200,
      });
      await sleep(stepSleepMs);
    }
    await client.flush();
    await printPhase(dashboardSession, "req_cap_breach", projectId, provider);
  };

  if (demoCase === "all") {
    await runSteady();
    await runNearCap();
    await runRetryStorm();
    await runLoopSuspect();
    await runTokenExplosion();
    await runCapBreach();
    await runReqCapBreach();
  } else if (demoCase === "steady") {
    await runSteady();
  } else if (demoCase === "near_cap") {
    await runNearCap();
  } else if (demoCase === "retry_storm") {
    await runRetryStorm();
  } else if (demoCase === "loop_suspect") {
    await runLoopSuspect();
  } else if (demoCase === "token_explosion") {
    await runTokenExplosion();
  } else if (demoCase === "cap_breach") {
    await runCapBreach();
  } else if (demoCase === "req_cap_breach") {
    await runReqCapBreach();
  } else {
    console.error(`Unsupported RHEONIC_DEMO_CASE: ${demoCase}`);
    printUsageExamples();
    process.exitCode = 1;
    client.close();
    return;
  }

  const expectedSent = demoCase === "all" ? 7 : 1;
  assertDelivery(client, expectedSent);
  log("[DONE] observe demo complete");
  client.close();
}

runDemo().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
