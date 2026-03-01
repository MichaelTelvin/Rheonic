import assert from "node:assert/strict";

import { createClient, instrumentAnthropic, instrumentGoogle, instrumentOpenAI, LLMTBGBlockedError } from "../dist/index.js";

const backendBaseUrl = process.env.LLMTBG_E2E_BACKEND_URL ?? "http://backend_test:8000";
const providerStubUrl = process.env.LLMTBG_E2E_PROVIDER_URL ?? "http://provider_stub_test:8099";

async function api(path, options = {}) {
  const mergedHeaders = {
    "Content-Type": "application/json",
    ...(options.headers ?? {}),
  };
  const response = await fetch(`${backendBaseUrl}${path}`, {
    ...options,
    headers: mergedHeaders,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`API ${path} failed (${response.status}): ${JSON.stringify(payload)}`);
  }
  return payload;
}

async function providerCount() {
  const response = await fetch(`${providerStubUrl}/count`);
  const payload = await response.json();
  return Number(payload.count ?? 0);
}

async function main() {
  const nonce = Date.now();
  const email = `node-e2e-${nonce}@example.com`;
  const password = "password123";

  await api("/api/v1/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
  const login = await api("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
  const authHeaders = { Authorization: `Bearer ${login.access_token}` };

  const project = await api("/api/v1/projects", {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({ name: `Node E2E ${nonce}` }),
  });

  await api(`/api/v1/projects/${project.id}/protect`, {
    method: "PUT",
    headers: authHeaders,
    body: JSON.stringify({
      protect_enabled: true,
      protect_fail_mode: "open",
      protect_max_req_per_min: 10000,
      protect_max_tok_per_min: 50000,
      protect_decision_timeout_ms: 100,
    }),
  });

  const createdKey = await api(`/api/v1/projects/${project.id}/keys`, {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({ name: "node-e2e" }),
  });

  await fetch(`${providerStubUrl}/reset`, { method: "POST" });
  const initialProviderCalls = await providerCount();

  const client = createClient({
    baseUrl: backendBaseUrl,
    ingestKey: createdKey.key,
    protectEnabled: true,
    flushIntervalMs: 60000,
  });
  const openai = {
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
    model: "gemini-1.5-pro",
    generateContent: async (prompt) => {
      await fetch(`${providerStubUrl}/call`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      return { usageMetadata: { promptTokenCount: 7, candidatesTokenCount: 5, totalTokenCount: 12 } };
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
  await googleModel.generateContent("google e2e smoke");
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
      messages: [{ role: "user", content: "Predictive warning near cap check for node e2e." }],
    });
  } catch (error) {
    blocked = error instanceof LLMTBGBlockedError;
  }
  assert.equal(blocked, false);
  assert.equal((await providerCount()) - initialProviderCalls, 4);

  const protectMetrics = await api(`/api/v1/metrics/protect?project_id=${encodeURIComponent(project.id)}`, {
    headers: authHeaders,
  });
  assert.ok(Number(protectMetrics.warned_60m ?? 0) >= 1);
  const openIncidents = await api(
    `/api/v1/incidents?project_id=${encodeURIComponent(project.id)}&status=open&provider=openai`,
    { headers: authHeaders },
  );
  assert.ok(Array.isArray(openIncidents));
  assert.ok(openIncidents.some((row) => row.type === "near_cap"));

  client.close();
  console.log("node protect e2e PASSED");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
