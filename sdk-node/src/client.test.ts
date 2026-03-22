import assert from "node:assert/strict";
import test from "node:test";

import { Client, captureEvent, createClient, instrumentOpenAI } from "./index.js";

function makeFetchStub() {
  const calls: Array<{ url: string; body?: string }> = [];
  const stub = (async (url: string, init?: RequestInit) => {
    calls.push({ url, body: typeof init?.body === "string" ? init.body : undefined });
    if (url.endsWith("/health")) {
      return { ok: true, status: 200, json: async () => ({ status: "ok" }) };
    }
    if (url.endsWith("/api/v1/protect/config")) {
      return { ok: true, status: 200, json: async () => ({ fail_mode: "open" }) };
    }
    if (url.endsWith("/api/v1/protect/decision")) {
      return { ok: true, status: 200, json: async () => ({ decision: "allow", reason: "ok" }) };
    }
    if (url.endsWith("/api/v1/events")) {
      return { ok: true, status: 202, json: async () => ({ status: "accepted" }) };
    }
    throw new Error(`Unexpected URL: ${url}`);
  }) as typeof fetch;
  return { calls, stub };
}

test("Client drops oldest events when the queue overflows", async () => {
  const originalFetch = globalThis.fetch;
  const { stub } = makeFetchStub();
  globalThis.fetch = stub;
  try {
    const client = new Client({ ingestKey: "k1", maxQueueSize: 1, overflowPolicy: "drop_oldest", flushIntervalMs: 30_000 });
    await client.captureEvent({ ts: "1", provider: "openai", model: null, environment: "dev", request: {}, response: { total_tokens: 1 } });
    await client.captureEvent({ ts: "2", provider: "openai", model: null, environment: "dev", request: {}, response: { total_tokens: 2 } });
    await client.flush();
    const stats = client.getStats();
    client.close();
    assert.equal(stats.dropped, 1);
    assert.equal(stats.sent, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("captureEvent helper is a no-op without a default client and instrumentOpenAI returns original client", async () => {
  await captureEvent({ provider: "openai", model: null, environment: "dev" });
  const openai = { chat: { completions: { create: async () => ({}) } } };
  assert.equal(instrumentOpenAI(openai), openai);
});

test("createClient replaces the default client and captureEvent sends built payloads", async () => {
  const originalFetch = globalThis.fetch;
  const { calls, stub } = makeFetchStub();
  globalThis.fetch = stub;
  try {
    const first = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const second = createClient({ ingestKey: "k2", flushIntervalMs: 30_000 });
    assert.notEqual(first, second);
    await captureEvent({ provider: "openai", model: "gpt-4o-mini", environment: "dev" });
    await second.flush();
    second.close();
    assert.ok(calls.some((call) => call.url.endsWith("/api/v1/events")));
  } finally {
    globalThis.fetch = originalFetch;
  }
});
