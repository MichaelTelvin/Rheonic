import assert from "node:assert/strict";

import { createClient, instrumentAnthropic, instrumentGoogle, instrumentOpenAI, RHEONICBlockedError } from "../dist/index.js";
import { DashboardSession } from "./dashboard_session.mjs";

const backendBaseUrl = process.env.RHEONIC_E2E_BACKEND_URL ?? "http://backend_test:8000";
const providerStubUrl = process.env.RHEONIC_E2E_PROVIDER_URL ?? "http://provider_stub_test:8099";

async function providerCount() {
  const response = await fetch(`${providerStubUrl}/count`);
  const payload = await response.json();
  return Number(payload.count ?? 0);
}

async function providerLastCall() {
  const response = await fetch(`${providerStubUrl}/last`);
  return await response.json();
}

function makeOpenAIStub() {
  return {
    chat: {
      completions: {
        create: async (payload) => {
          await fetch(`${providerStubUrl}/call`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          return { model: payload.model ?? "gpt-4o-mini", usage: { total_tokens: 10 } };
        },
      },
    },
  };
}

async function main() {
  const nonce = Date.now();
  const email = `node-e2e-${nonce}@example.com`;
  const password = "Password123!";
  const session = new DashboardSession(backendBaseUrl);

  await session.request("/api/v1/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
  await session.login(email, password);

  const project = await session.request("/api/v1/projects", {
    method: "POST",
    body: JSON.stringify({ name: `Node E2E ${nonce}` }),
  });

  await session.request(`/api/v1/projects/${project.id}/protect`, {
    method: "PUT",
    body: JSON.stringify({
      protect_enabled: true,
      protect_fail_mode: "open",
      apply_clamp: false,
      protect_max_req_per_min: 10000,
      protect_max_tok_per_min: 50000,
    }),
  });

  const createdKey = await session.request(`/api/v1/projects/${project.id}/keys`, {
    method: "POST",
    body: JSON.stringify({ name: "node-e2e" }),
  });

  const preflightResponse = await fetch(`${backendBaseUrl}/api/v1/protect/decision`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Project-Ingest-Key": createdKey.key,
    },
    body: JSON.stringify({
      provider: "openai",
      model: "gpt-4o-mini",
      environment: "dev",
      feature: "node-e2e",
      input_tokens_estimate: 12,
      max_output_tokens: 32,
    }),
  });
  assert.equal(preflightResponse.status, 200);
  assert.ok(Number(preflightResponse.headers.get("X-Protect-Decision-Latency-Ms")) >= 0);

  await fetch(`${providerStubUrl}/reset`, { method: "POST" });
  const initialProviderCalls = await providerCount();

  const client = createClient({
    baseUrl: backendBaseUrl,
    ingestKey: createdKey.key,
    flushIntervalMs: 60000,
  });
  const openai = makeOpenAIStub();
  const anthropic = {
    messages: {
      create: async (payload) => {
        await fetch(`${providerStubUrl}/call`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        return {
          model: payload.model ?? "claude-3-5-sonnet-20240620",
          usage: { input_tokens: 8, output_tokens: 6, total_tokens: 14 },
        };
      },
    },
  };
  const googleModel = {
    models: {
      generateContent: async (payload) => {
        await fetch(`${providerStubUrl}/call`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        return { usageMetadata: { promptTokenCount: 7, candidatesTokenCount: 5, totalTokenCount: 12 } };
      },
    },
  };

  instrumentOpenAI(openai, { client, feature: "node-e2e" });
  instrumentAnthropic(anthropic, { client, feature: "node-e2e" });
  instrumentGoogle(googleModel, { client, feature: "node-e2e" });

  await openai.chat.completions.create({ model: "gpt-4o-mini", max_tokens: 128, input_tokens: 10 });
  await anthropic.messages.create({
    model: "claude-3-5-sonnet-20240620",
    max_tokens: 128,
    messages: [{ role: "user", content: "anthropic e2e smoke" }],
  });
  await googleModel.models.generateContent({
    model: "gemini-1.5-pro",
    contents: "google e2e smoke",
  });
  assert.equal((await providerCount()) - initialProviderCalls, 3);

  const nowIso = new Date().toISOString();
  const ingestResponse = await fetch(`${backendBaseUrl}/api/v1/events`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Project-Ingest-Key": createdKey.key,
    },
    body: JSON.stringify({
      ts: nowIso,
      provider: "openai",
      model: "gpt-4o-mini",
      environment: "dev",
      response: { total_tokens: 49000 },
    }),
  });
  assert.equal(ingestResponse.status, 202);

  let blocked = false;
  try {
    await openai.chat.completions.create({
      model: "gpt-4o-mini",
      max_tokens: 2000,
      messages: [{ role: "user", content: "Clamp-off allow check for node e2e." }],
    });
  } catch (error) {
    blocked = error instanceof RHEONICBlockedError;
  }
  assert.equal(blocked, false);
  assert.equal((await providerCount()) - initialProviderCalls, 4);
  assert.equal(Number((await providerLastCall()).payload?.max_tokens ?? 0), 2000);

  await session.request(`/api/v1/projects/${project.id}/protect`, {
    method: "PUT",
    body: JSON.stringify({
      protect_enabled: true,
      protect_fail_mode: "open",
      apply_clamp: true,
      protect_max_req_per_min: 10000,
      protect_max_tok_per_min: 50000,
    }),
  });

  blocked = false;
  try {
    await openai.chat.completions.create({
      model: "gpt-4o-mini",
      max_tokens: 2000,
      messages: [{ role: "user", content: "Clamp-on check for node e2e." }],
    });
  } catch (error) {
    blocked = error instanceof RHEONICBlockedError;
  }
  assert.equal(blocked, false);
  assert.equal((await providerCount()) - initialProviderCalls, 5);
  const clampedMaxTokens = Number((await providerLastCall()).payload?.max_tokens ?? 0);
  assert.ok(clampedMaxTokens > 0 && clampedMaxTokens < 2000);

  const protectMetrics = await session.request(`/api/v1/metrics/protect?project_id=${encodeURIComponent(project.id)}`);
  assert.ok(Number(protectMetrics.clamped_60m ?? 0) >= 1);
  const openIncidents = await session.request(`/api/v1/incidents?project_id=${encodeURIComponent(project.id)}&status=open&provider=openai`);
  assert.ok(Array.isArray(openIncidents));
  assert.ok(openIncidents.every((row) => row.type !== "block"));

  const metricsBeforeCooldown = await session.request(`/api/v1/metrics/protect?project_id=${encodeURIComponent(project.id)}`);
  const blockedBeforeCooldown = Number(metricsBeforeCooldown.blocked_60m ?? 0);

  await session.request(`/api/v1/projects/${project.id}/protect`, {
    method: "PUT",
    body: JSON.stringify({
      protect_enabled: true,
      protect_fail_mode: "open",
      apply_clamp: false,
      protect_max_req_per_min: 1,
      protect_max_tok_per_min: 50000,
    }),
  });

  let firstBlockReason = "";
  try {
    await openai.chat.completions.create({
      model: "gpt-4o-mini",
      max_tokens: 128,
      messages: [{ role: "user", content: "Cooldown backend block check." }],
    });
  } catch (error) {
    assert.ok(error instanceof RHEONICBlockedError);
    firstBlockReason = error.reason;
  }
  assert.equal(firstBlockReason, "req_cap_breach");
  assert.equal((await providerCount()) - initialProviderCalls, 5);

  const metricsAfterInitialBlock = await session.request(`/api/v1/metrics/protect?project_id=${encodeURIComponent(project.id)}`);
  assert.equal(Number(metricsAfterInitialBlock.blocked_60m ?? 0), blockedBeforeCooldown + 1);
  assert.equal(String(metricsAfterInitialBlock.last?.reason ?? ""), "req_cap_breach");
  assert.equal(String(metricsAfterInitialBlock.last?.source ?? ""), "live");

  let localCooldownReason = "";
  try {
    await openai.chat.completions.create({
      model: "gpt-4o-mini",
      max_tokens: 128,
      messages: [{ role: "user", content: "Cooldown local cached block check." }],
    });
  } catch (error) {
    assert.ok(error instanceof RHEONICBlockedError);
    localCooldownReason = error.reason;
  }
  assert.equal(localCooldownReason, "cooldown_active");
  assert.equal((await providerCount()) - initialProviderCalls, 5);

  const metricsAfterLocalCooldown = await session.request(`/api/v1/metrics/protect?project_id=${encodeURIComponent(project.id)}`);
  assert.equal(Number(metricsAfterLocalCooldown.blocked_60m ?? 0), blockedBeforeCooldown + 1);
  assert.equal(String(metricsAfterLocalCooldown.last?.reason ?? ""), "req_cap_breach");

  const cooldownClient = createClient({
    baseUrl: backendBaseUrl,
    ingestKey: createdKey.key,
    flushIntervalMs: 60000,
  });
  await cooldownClient.warmConnections();
  const cooldownOpenAI = makeOpenAIStub();
  instrumentOpenAI(cooldownOpenAI, { client: cooldownClient, feature: "node-e2e-cooldown" });

  let backendCooldownReason = "";
  try {
    await cooldownOpenAI.chat.completions.create({
      model: "gpt-4o-mini",
      max_tokens: 128,
      messages: [{ role: "user", content: "Cooldown backend live decision check." }],
    });
  } catch (error) {
    assert.ok(error instanceof RHEONICBlockedError);
    backendCooldownReason = error.reason;
  }
  assert.equal(backendCooldownReason, "cooldown_active");
  assert.equal((await providerCount()) - initialProviderCalls, 5);

  const metricsAfterBackendCooldown = await session.request(`/api/v1/metrics/protect?project_id=${encodeURIComponent(project.id)}`);
  assert.equal(Number(metricsAfterBackendCooldown.blocked_60m ?? 0), blockedBeforeCooldown + 2);
  assert.equal(String(metricsAfterBackendCooldown.last?.reason ?? ""), "cooldown_active");
  assert.equal(String(metricsAfterBackendCooldown.last?.source ?? ""), "live");

  cooldownClient.close();
  client.close();
  await session.request("/api/v1/auth/logout", { method: "POST" }, false);
  console.log("node protect e2e PASSED");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
