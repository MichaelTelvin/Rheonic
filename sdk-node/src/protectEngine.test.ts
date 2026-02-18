import test from "node:test";
import assert from "node:assert/strict";

import { createClient, instrumentOpenAI, LLMTBGBlockedError } from "./index.js";

function makeOpenAIStub() {
  const calls: Array<unknown[]> = [];
  const openai = {
    chat: {
      completions: {
        create: async (...args: unknown[]) => {
          calls.push(args);
          return { model: "gpt-4o-mini", usage: { total_tokens: 42 } };
        },
      },
    },
  };
  return { openai, calls };
}

test("decision block prevents provider call", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    ({
      ok: true,
      status: 200,
      json: async () => ({
        decision: "block",
        reason: "tok_limit",
        fail_mode: "open",
        protect_decision_timeout_ms: 100,
      }),
    }) as Response) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), LLMTBGBlockedError);
    assert.equal(calls.length, 0);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("decision warn allows provider call", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    ({
      ok: true,
      status: 200,
      json: async () => ({
        decision: "warn",
        reason: "incident_medium",
        fail_mode: "open",
        protect_decision_timeout_ms: 100,
      }),
    }) as Response) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({ model: "gpt-4o-mini", max_tokens: 256 });
    assert.equal(calls.length, 1);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("decision timeout fail-open allows provider call", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    throw new Error("network timeout");
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000, protectFailMode: "open" });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({ model: "gpt-4o-mini" });
    assert.equal(calls.length, 1);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("decision timeout fail-closed blocks provider call", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    throw new Error("network timeout");
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000, protectFailMode: "closed" });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), LLMTBGBlockedError);
    assert.equal(calls.length, 0);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});
