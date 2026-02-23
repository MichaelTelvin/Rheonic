import test from "node:test";
import assert from "node:assert/strict";

import { createClient, instrumentOpenAI, LLMTBGBlockedError } from "./index.js";
import { __setInputTokenEstimatorForTests } from "./providers/openaiAdapter.js";

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

test("observe mode skips decision endpoint and still calls provider", async () => {
  const originalFetch = globalThis.fetch;
  let decisionCalls = 0;
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      decisionCalls += 1;
      return {
        ok: true,
        status: 200,
        json: async () => ({ decision: "block", reason: "tok_limit" }),
      } as Response;
    }
    if (url.endsWith("/api/v1/events")) {
      return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
    }
    throw new Error(`Unexpected URL: ${url}`);
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", protectEnabled: false, flushIntervalMs: 30_000 });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({ model: "gpt-4o-mini" });
    await client.flush();
    assert.equal(calls.length, 1);
    assert.equal(decisionCalls, 0);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("observe mode skips token estimation", async () => {
  const originalFetch = globalThis.fetch;
  let estimatorCalls = 0;
  __setInputTokenEstimatorForTests(() => {
    estimatorCalls += 1;
    return 111;
  });
  globalThis.fetch = (async (url: string) => {
    if (url.endsWith("/api/v1/events")) {
      return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
    }
    throw new Error(`Unexpected URL: ${url}`);
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", protectEnabled: false, flushIntervalMs: 30_000 });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: "hello" }],
    });
    await client.flush();
    assert.equal(calls.length, 1);
    assert.equal(estimatorCalls, 0);
    client.close();
  } finally {
    __setInputTokenEstimatorForTests(null);
    globalThis.fetch = originalFetch;
  }
});

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
    const client = createClient({ protectEnabled: true, ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), LLMTBGBlockedError);
    assert.equal(calls.length, 0);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("blocked_until short-circuits subsequent decision calls locally", async () => {
  const originalFetch = globalThis.fetch;
  let decisionCalls = 0;
  const blockedUntil = new Date(Date.now() + 60_000).toISOString();
  globalThis.fetch = (async (url: string) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      decisionCalls += 1;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          decision: "block",
          reason: "req_limit",
          fail_mode: "open",
          protect_decision_timeout_ms: 100,
          blocked_until: blockedUntil,
        }),
      } as Response;
    }
    throw new Error(`Unexpected URL: ${url}`);
  }) as typeof fetch;

  try {
    const client = createClient({ protectEnabled: true, ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), LLMTBGBlockedError);
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), LLMTBGBlockedError);
    assert.equal(decisionCalls, 1);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("parallel calls during active cooldown block locally without backend decision calls", async () => {
  const originalFetch = globalThis.fetch;
  let decisionCalls = 0;
  const blockedUntil = new Date(Date.now() + 60_000).toISOString();
  globalThis.fetch = (async (url: string) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      decisionCalls += 1;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          decision: "block",
          reason: "req_limit",
          fail_mode: "open",
          protect_decision_timeout_ms: 100,
          blocked_until: blockedUntil,
        }),
      } as Response;
    }
    throw new Error(`Unexpected URL: ${url}`);
  }) as typeof fetch;

  try {
    const client = createClient({ protectEnabled: true, ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });

    // Prime cooldown from backend once.
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), LLMTBGBlockedError);
    assert.equal(decisionCalls, 1);

    // During active cooldown, both concurrent calls should short-circuit locally.
    const first = openai.chat.completions.create({ model: "gpt-4o-mini" });
    const second = openai.chat.completions.create({ model: "gpt-4o-mini" });
    const results = await Promise.allSettled([first, second]);
    assert.equal(results[0].status, "rejected");
    assert.equal(results[1].status, "rejected");
    assert.equal(decisionCalls, 1);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("predictive_near_cap warn allows provider call", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    ({
      ok: true,
      status: 200,
      json: async () => ({
        decision: "warn",
        reason: "predictive_near_cap",
        fail_mode: "open",
        protect_decision_timeout_ms: 100,
      }),
    }) as Response) as typeof fetch;

  try {
    const client = createClient({ protectEnabled: true, ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({ model: "gpt-4o-mini", max_tokens: 2048 });
    assert.equal(calls.length, 1);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("decision warn allows provider call and tags telemetry", async () => {
  const originalFetch = globalThis.fetch;
  const ingestedEvents: Array<Record<string, unknown>> = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          decision: "warn",
          reason: "incident_medium",
          fail_mode: "open",
          protect_decision_timeout_ms: 100,
        }),
      } as Response;
    }
    if (url.endsWith("/api/v1/events")) {
      if (init?.body && typeof init.body === "string") {
        ingestedEvents.push(JSON.parse(init.body) as Record<string, unknown>);
      }
      return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
    }
    throw new Error(`Unexpected URL: ${url}`);
  }) as typeof fetch;

  try {
    const client = createClient({ protectEnabled: true, ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({ model: "gpt-4o-mini", max_tokens: 256 });
    await client.flush();
    assert.equal(calls.length, 1);
    assert.equal(ingestedEvents.length, 1);
    const request = (ingestedEvents[0].request ?? {}) as Record<string, unknown>;
    assert.equal(request.protect_decision, "warn");
    assert.equal(request.protect_reason, "incident_medium");
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("messages request includes estimated input_tokens_estimate in protect payload", async () => {
  const originalFetch = globalThis.fetch;
  const decisionBodies: Array<Record<string, unknown>> = [];
  __setInputTokenEstimatorForTests(() => 321);
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      if (typeof init?.body === "string") {
        decisionBodies.push(JSON.parse(init.body) as Record<string, unknown>);
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          decision: "allow",
          reason: "ok",
          fail_mode: "open",
          protect_decision_timeout_ms: 100,
        }),
      } as Response;
    }
    return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
  }) as typeof fetch;

  try {
    const client = createClient({ protectEnabled: true, ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: "hello world" }],
      max_tokens: 128,
    });
    assert.equal(decisionBodies.length, 1);
    assert.equal(decisionBodies[0].input_tokens_estimate, 321);
    client.close();
  } finally {
    __setInputTokenEstimatorForTests(null);
    globalThis.fetch = originalFetch;
  }
});

test("messages request sends default-on input_tokens_estimate without overrides", async () => {
  const originalFetch = globalThis.fetch;
  const decisionBodies: Array<Record<string, unknown>> = [];
  __setInputTokenEstimatorForTests(null);
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      if (typeof init?.body === "string") {
        decisionBodies.push(JSON.parse(init.body) as Record<string, unknown>);
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          decision: "allow",
          reason: "ok",
          fail_mode: "open",
          protect_decision_timeout_ms: 100,
        }),
      } as Response;
    }
    return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
  }) as typeof fetch;

  try {
    const client = createClient({ protectEnabled: true, ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: "hello world" }],
      max_tokens: 128,
    });
    assert.equal(decisionBodies.length, 1);
    const estimate = decisionBodies[0].input_tokens_estimate;
    assert.equal(typeof estimate, "number");
    assert.ok((estimate as number) > 0);
    client.close();
  } finally {
    __setInputTokenEstimatorForTests(null);
    globalThis.fetch = originalFetch;
  }
});

test("token estimation failure omits input_tokens_estimate from protect payload", async () => {
  const originalFetch = globalThis.fetch;
  const decisionBodies: Array<Record<string, unknown>> = [];
  __setInputTokenEstimatorForTests(() => null);
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      if (typeof init?.body === "string") {
        decisionBodies.push(JSON.parse(init.body) as Record<string, unknown>);
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          decision: "allow",
          reason: "ok",
          fail_mode: "open",
          protect_decision_timeout_ms: 100,
        }),
      } as Response;
    }
    return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
  }) as typeof fetch;

  try {
    const client = createClient({ protectEnabled: true, ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: "hello world" }],
      max_tokens: 128,
    });
    assert.equal(decisionBodies.length, 1);
    assert.equal("input_tokens_estimate" in decisionBodies[0], false);
    client.close();
  } finally {
    __setInputTokenEstimatorForTests(null);
    globalThis.fetch = originalFetch;
  }
});

test("request with no messages or prompt omits input_tokens_estimate", async () => {
  const originalFetch = globalThis.fetch;
  const decisionBodies: Array<Record<string, unknown>> = [];
  __setInputTokenEstimatorForTests(null);
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      if (typeof init?.body === "string") {
        decisionBodies.push(JSON.parse(init.body) as Record<string, unknown>);
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          decision: "allow",
          reason: "ok",
          fail_mode: "open",
          protect_decision_timeout_ms: 100,
        }),
      } as Response;
    }
    return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
  }) as typeof fetch;

  try {
    const client = createClient({ protectEnabled: true, ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({
      model: "gpt-4o-mini",
      max_tokens: 128,
    });
    assert.equal(decisionBodies.length, 1);
    assert.equal("input_tokens_estimate" in decisionBodies[0], false);
    client.close();
  } finally {
    __setInputTokenEstimatorForTests(null);
    globalThis.fetch = originalFetch;
  }
});

test("decision timeout fail-open allows provider call", async () => {
  const originalFetch = globalThis.fetch;
  const timeoutReports: Array<Record<string, unknown>> = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision-timeout")) {
      timeoutReports.push(typeof init?.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : {});
      return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
    }
    if (url.endsWith("/api/v1/protect/decision")) {
      const abortError = new Error("aborted");
      (abortError as Error & { name: string }).name = "AbortError";
      throw abortError;
    }
    throw new Error(`Unexpected URL: ${url}`);
  }) as typeof fetch;

  try {
    const client = createClient({
      protectEnabled: true,
      ingestKey: "k1",
      environment: "dev",
      flushIntervalMs: 30_000,
      protectFailMode: "open",
      protectDecisionTimeoutMs: 5,
    });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({ model: "gpt-4o-mini" });
    assert.equal(calls.length, 1);
    assert.equal(timeoutReports.length, 1);
    assert.equal(timeoutReports[0].environment, "dev");
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("decision timeout fail-closed blocks provider call", async () => {
  const originalFetch = globalThis.fetch;
  const timeoutReports: Array<Record<string, unknown>> = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision-timeout")) {
      timeoutReports.push(typeof init?.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : {});
      return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
    }
    if (url.endsWith("/api/v1/protect/decision")) {
      const abortError = new Error("aborted");
      (abortError as Error & { name: string }).name = "AbortError";
      throw abortError;
    }
    throw new Error(`Unexpected URL: ${url}`);
  }) as typeof fetch;

  try {
    const client = createClient({
      protectEnabled: true,
      ingestKey: "k1",
      environment: "staging",
      flushIntervalMs: 30_000,
      protectFailMode: "closed",
      protectDecisionTimeoutMs: 5,
    });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), LLMTBGBlockedError);
    assert.equal(calls.length, 0);
    assert.equal(timeoutReports.length, 1);
    assert.equal(timeoutReports[0].environment, "staging");
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("decision 500 fail-open allows provider call", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    ({
      ok: false,
      status: 500,
      json: async () => ({ error: "server" }),
    }) as Response) as typeof fetch;

  try {
    const client = createClient({ protectEnabled: true, ingestKey: "k1", flushIntervalMs: 30_000, protectFailMode: "open" });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({ model: "gpt-4o-mini" });
    assert.equal(calls.length, 1);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("decision 500 fail-closed blocks provider call", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    ({
      ok: false,
      status: 500,
      json: async () => ({ error: "server" }),
    }) as Response) as typeof fetch;

  try {
    const client = createClient({ protectEnabled: true, ingestKey: "k1", flushIntervalMs: 30_000, protectFailMode: "closed" });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), LLMTBGBlockedError);
    assert.equal(calls.length, 0);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("invalid JSON fail-open allows provider call", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    ({
      ok: true,
      status: 200,
      json: async () => {
        throw new Error("invalid json");
      },
    }) as unknown as Response) as typeof fetch;

  try {
    const client = createClient({ protectEnabled: true, ingestKey: "k1", flushIntervalMs: 30_000, protectFailMode: "open" });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({ model: "gpt-4o-mini" });
    assert.equal(calls.length, 1);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("invalid JSON fail-closed blocks provider call", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    ({
      ok: true,
      status: 200,
      json: async () => {
        throw new Error("invalid json");
      },
    }) as unknown as Response) as typeof fetch;

  try {
    const client = createClient({ protectEnabled: true, ingestKey: "k1", flushIntervalMs: 30_000, protectFailMode: "closed" });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), LLMTBGBlockedError);
    assert.equal(calls.length, 0);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});
