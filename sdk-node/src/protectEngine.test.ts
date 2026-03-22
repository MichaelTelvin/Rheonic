import assert from "node:assert/strict";
import test from "node:test";

import {
  createClient,
  instrumentAnthropic,
  instrumentGoogle,
  instrumentOpenAI,
  RHEONICBlockedError,
  RHEONICValidationError,
} from "./index.js";
import { validateProviderModel } from "./providerModelValidation.js";
import { __setInputTokenEstimatorForTests as __setAnthropicEstimatorForTests } from "./providers/anthropicAdapter.js";
import { __setInputTokenEstimatorForTests as __setGoogleEstimatorForTests } from "./providers/googleAdapter.js";
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

function makeAnthropicStub() {
  const calls: Array<unknown[]> = [];
  const anthropic = {
    messages: {
      create: async (...args: unknown[]) => {
        calls.push(args);
        return { model: "claude-3-5-sonnet", usage: { input_tokens: 12, output_tokens: 28 } };
      },
    },
  };
  return { anthropic, calls };
}

function makeGoogleStub() {
  const calls: Array<unknown[]> = [];
  const googleModel = {
    model: "gemini-1.5-pro",
    generateContent: async (...args: unknown[]) => {
      calls.push(args);
      return { response: { usageMetadata: { totalTokenCount: 35 } } };
    },
  };
  return { googleModel, calls };
}

test("preflight decision endpoint is always called before provider request", async () => {
  const originalFetch = globalThis.fetch;
  let decisionCalls = 0;
  globalThis.fetch = (async (url: string) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      decisionCalls += 1;
      return {
        ok: true,
        status: 200,
        json: async () => ({ decision: "allow", reason: "ok" }),
      } as Response;
    }
    if (url.endsWith("/api/v1/events")) {
      return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
    }
    throw new Error(`Unexpected URL: ${url}`);
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({ model: "gpt-4o-mini" });
    await client.flush();
    assert.equal(calls.length, 1);
    assert.equal(decisionCalls, 1);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("token estimation is evaluated before protect decision request", async () => {
  const originalFetch = globalThis.fetch;
  let estimatorCalls = 0;
  __setInputTokenEstimatorForTests(() => {
    estimatorCalls += 1;
    return 111;
  });
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      const parsed = init?.body ? (JSON.parse(String(init.body)) as { input_tokens_estimate?: unknown }) : {};
      assert.equal(parsed.input_tokens_estimate, 111);
      return {
        ok: true,
        status: 200,
        json: async () => ({ decision: "allow", reason: "ok" }),
      } as Response;
    }
    if (url.endsWith("/api/v1/events")) {
      return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
    }
    throw new Error(`Unexpected URL: ${url}`);
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: "hello" }],
    });
    await client.flush();
    assert.equal(calls.length, 1);
    assert.equal(estimatorCalls, 1);
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
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), RHEONICBlockedError);
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
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), RHEONICBlockedError);
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), RHEONICBlockedError);
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
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });

    // Prime cooldown from backend once.
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), RHEONICBlockedError);
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

test("near_cap warn allows provider call", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    ({
      ok: true,
      status: 200,
      json: async () => ({
        decision: "warn",
        reason: "near_cap",
        fail_mode: "open",
        protect_decision_timeout_ms: 100,
      }),
    }) as Response) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
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
          reason: "retry_storm",
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
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({ model: "gpt-4o-mini", max_tokens: 256 });
    await client.flush();
    assert.equal(calls.length, 1);
    assert.equal(ingestedEvents.length, 1);
    const request = (ingestedEvents[0].request ?? {}) as Record<string, unknown>;
    assert.equal(request.protect_decision, "warn");
    assert.equal(request.protect_reason, "retry_storm");
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
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
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
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
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
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
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
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
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
      ingestKey: "k1",
      environment: "dev",
      flushIntervalMs: 30_000,
      protectFailMode: "open",
    });
    ((client as unknown as { protectEngine?: { decisionTimeoutMs?: number } }).protectEngine ?? {}).decisionTimeoutMs = 5;
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({ model: "gpt-4o-mini" });
    assert.equal(calls.length, 1);
    assert.equal(timeoutReports.length, 1);
    assert.equal(timeoutReports[0].environment, "dev");
    assert.equal(timeoutReports[0].provider, "openai");
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
      ingestKey: "k1",
      environment: "staging",
      flushIntervalMs: 30_000,
      protectFailMode: "closed",
    });
    ((client as unknown as { protectEngine?: { decisionTimeoutMs?: number } }).protectEngine ?? {}).decisionTimeoutMs = 5;
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), RHEONICBlockedError);
    assert.equal(calls.length, 0);
    assert.equal(timeoutReports.length, 1);
    assert.equal(timeoutReports[0].environment, "staging");
    assert.equal(timeoutReports[0].provider, "openai");
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("decision 500 fail-open allows provider call", async () => {
  const originalFetch = globalThis.fetch;
  const unavailableReports: Array<Record<string, unknown>> = [];
  globalThis.fetch = (async () =>
    ({
      ok: false,
      status: 500,
      json: async () => ({ error: "server" }),
    }) as Response) as typeof fetch;
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision-unavailable")) {
      unavailableReports.push(typeof init?.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : {});
      return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
    }
    return {
      ok: false,
      status: 500,
      json: async () => ({ error: "server" }),
    } as Response;
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000, protectFailMode: "open" });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({ model: "gpt-4o-mini" });
    assert.equal(calls.length, 1);
    assert.equal(unavailableReports.length, 1);
    assert.equal(unavailableReports[0].provider, "openai");
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("decision 500 fail-closed blocks provider call", async () => {
  const originalFetch = globalThis.fetch;
  const unavailableReports: Array<Record<string, unknown>> = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision-unavailable")) {
      unavailableReports.push(typeof init?.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : {});
      return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
    }
    return {
      ok: false,
      status: 500,
      json: async () => ({ error: "server" }),
    } as Response;
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000, protectFailMode: "closed" });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), RHEONICBlockedError);
    assert.equal(calls.length, 0);
    assert.equal(unavailableReports.length, 1);
    assert.equal(unavailableReports[0].provider, "openai");
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("invalid JSON fail-open allows provider call", async () => {
  const originalFetch = globalThis.fetch;
  const unavailableReports: Array<Record<string, unknown>> = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision-unavailable")) {
      unavailableReports.push(typeof init?.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : {});
      return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
    }
    return {
      ok: true,
      status: 200,
      json: async () => {
        throw new Error("invalid json");
      },
    } as unknown as Response;
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000, protectFailMode: "open" });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await openai.chat.completions.create({ model: "gpt-4o-mini" });
    assert.equal(calls.length, 1);
    assert.equal(unavailableReports.length, 1);
    assert.equal(unavailableReports[0].provider, "openai");
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("invalid JSON fail-closed blocks provider call", async () => {
  const originalFetch = globalThis.fetch;
  const unavailableReports: Array<Record<string, unknown>> = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision-unavailable")) {
      unavailableReports.push(typeof init?.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : {});
      return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
    }
    return {
      ok: true,
      status: 200,
      json: async () => {
        throw new Error("invalid json");
      },
    } as unknown as Response;
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000, protectFailMode: "closed" });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await assert.rejects(() => openai.chat.completions.create({ model: "gpt-4o-mini" }), RHEONICBlockedError);
    assert.equal(calls.length, 0);
    assert.equal(unavailableReports.length, 1);
    assert.equal(unavailableReports[0].provider, "openai");
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("anthropic allow path calls provider and emits telemetry", async () => {
  const originalFetch = globalThis.fetch;
  const ingestedEvents: Array<Record<string, unknown>> = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ decision: "allow", reason: "ok", fail_mode: "open", protect_decision_timeout_ms: 100 }),
      } as Response;
    }
    if (url.endsWith("/api/v1/events")) {
      if (typeof init?.body === "string") {
        ingestedEvents.push(JSON.parse(init.body) as Record<string, unknown>);
      }
      return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
    }
    throw new Error(`Unexpected URL: ${url}`);
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { anthropic, calls } = makeAnthropicStub();
    instrumentAnthropic(anthropic, { client });
    await anthropic.messages.create({
      model: "claude-3-5-sonnet",
      max_tokens: 256,
      messages: [{ role: "user", content: "hello" }],
    });
    await client.flush();
    assert.equal(calls.length, 1);
    assert.equal(ingestedEvents.length, 1);
    assert.equal(ingestedEvents[0].provider, "anthropic");
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("anthropic block path prevents provider call", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    ({
      ok: true,
      status: 200,
      json: async () => ({ decision: "block", reason: "tok_limit", fail_mode: "open", protect_decision_timeout_ms: 100 }),
    }) as Response) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { anthropic, calls } = makeAnthropicStub();
    instrumentAnthropic(anthropic, { client });
    await assert.rejects(
      () => anthropic.messages.create({ model: "claude-3-5-sonnet", max_tokens: 128, messages: [{ role: "user", content: "hello" }] }),
      RHEONICBlockedError,
    );
    assert.equal(calls.length, 0);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("anthropic includes input_tokens_estimate in decision payload", async () => {
  const originalFetch = globalThis.fetch;
  const decisionBodies: Array<Record<string, unknown>> = [];
  __setAnthropicEstimatorForTests(() => 456);
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      if (typeof init?.body === "string") {
        decisionBodies.push(JSON.parse(init.body) as Record<string, unknown>);
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ decision: "allow", reason: "ok", fail_mode: "open", protect_decision_timeout_ms: 100 }),
      } as Response;
    }
    return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { anthropic } = makeAnthropicStub();
    instrumentAnthropic(anthropic, { client });
    await anthropic.messages.create({
      model: "claude-3-5-sonnet",
      max_tokens: 128,
      messages: [{ role: "user", content: "hello world" }],
    });
    assert.equal(decisionBodies.length, 1);
    assert.equal(decisionBodies[0].input_tokens_estimate, 456);
    client.close();
  } finally {
    __setAnthropicEstimatorForTests(null);
    globalThis.fetch = originalFetch;
  }
});

test("google allow path calls provider and emits telemetry", async () => {
  const originalFetch = globalThis.fetch;
  const ingestedEvents: Array<Record<string, unknown>> = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ decision: "allow", reason: "ok", fail_mode: "open", protect_decision_timeout_ms: 100 }),
      } as Response;
    }
    if (url.endsWith("/api/v1/events")) {
      if (typeof init?.body === "string") {
        ingestedEvents.push(JSON.parse(init.body) as Record<string, unknown>);
      }
      return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
    }
    throw new Error(`Unexpected URL: ${url}`);
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { googleModel, calls } = makeGoogleStub();
    instrumentGoogle(googleModel, { client });
    await googleModel.generateContent("hello from google");
    await client.flush();
    assert.equal(calls.length, 1);
    assert.equal(ingestedEvents.length, 1);
    assert.equal(ingestedEvents[0].provider, "google");
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("google block path prevents provider call", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    ({
      ok: true,
      status: 200,
      json: async () => ({ decision: "block", reason: "req_limit", fail_mode: "open", protect_decision_timeout_ms: 100 }),
    }) as Response) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { googleModel, calls } = makeGoogleStub();
    instrumentGoogle(googleModel, { client });
    await assert.rejects(() => googleModel.generateContent("hello"), RHEONICBlockedError);
    assert.equal(calls.length, 0);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("google includes input_tokens_estimate in decision payload", async () => {
  const originalFetch = globalThis.fetch;
  const decisionBodies: Array<Record<string, unknown>> = [];
  __setGoogleEstimatorForTests(() => 654);
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      if (typeof init?.body === "string") {
        decisionBodies.push(JSON.parse(init.body) as Record<string, unknown>);
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ decision: "allow", reason: "ok", fail_mode: "open", protect_decision_timeout_ms: 100 }),
      } as Response;
    }
    return { ok: true, status: 202, json: async () => ({ status: "accepted" }) } as Response;
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { googleModel } = makeGoogleStub();
    instrumentGoogle(googleModel, { client });
    await googleModel.generateContent("hello world");
    assert.equal(decisionBodies.length, 1);
    assert.equal(decisionBodies[0].input_tokens_estimate, 654);
    client.close();
  } finally {
    __setGoogleEstimatorForTests(null);
    globalThis.fetch = originalFetch;
  }
});

test("provider/model validation accepts openai gpt model", async () => {
  const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
  const { openai, calls } = makeOpenAIStub();
  instrumentOpenAI(openai, { client });
  await openai.chat.completions.create({ model: "gpt-4o-mini" });
  assert.equal(calls.length, 1);
  client.close();
});

test("provider/model validation accepts anthropic claude model", async () => {
  const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
  const { anthropic, calls } = makeAnthropicStub();
  instrumentAnthropic(anthropic, { client });
  await anthropic.messages.create({
    model: "claude-3-5-sonnet",
    max_tokens: 64,
    messages: [{ role: "user", content: "hello" }],
  });
  assert.equal(calls.length, 1);
  client.close();
});

test("provider/model validation accepts google model", async () => {
  const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
  const { googleModel, calls } = makeGoogleStub();
  instrumentGoogle(googleModel, { client });
  await googleModel.generateContent("hello");
  assert.equal(calls.length, 1);
  client.close();
});

test("provider/model validation does not enforce naming prefixes", async () => {
  const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
  const { anthropic, calls: anthropicCalls } = makeAnthropicStub();
  instrumentAnthropic(anthropic, { client });
  await anthropic.messages.create({
    model: "gpt-4o-mini",
    max_tokens: 64,
    messages: [{ role: "user", content: "hello" }],
  });

  const { googleModel, calls: googleCalls } = makeGoogleStub();
  (googleModel as { model: string }).model = "claude-3-opus";
  instrumentGoogle(googleModel, { client });
  await googleModel.generateContent("hello");

  assert.equal(anthropicCalls.length, 1);
  assert.equal(googleCalls.length, 1);
  client.close();
});

test("provider/model validation rejects anthropic call when model is missing", async () => {
  const originalFetch = globalThis.fetch;
  let decisionCalls = 0;
  globalThis.fetch = (async (url: string) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      decisionCalls += 1;
    }
    return { ok: true, status: 202, json: async () => ({}) } as Response;
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { anthropic, calls } = makeAnthropicStub();
    instrumentAnthropic(anthropic, { client });
    await assert.rejects(
      () =>
        anthropic.messages.create({
          max_tokens: 64,
          messages: [{ role: "user", content: "hello" }],
        }),
      RHEONICValidationError,
    );
    assert.equal(calls.length, 0);
    assert.equal(decisionCalls, 0);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("provider/model validation rejects openai call when model is missing", async () => {
  const originalFetch = globalThis.fetch;
  let decisionCalls = 0;
  globalThis.fetch = (async (url: string) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      decisionCalls += 1;
    }
    return { ok: true, status: 202, json: async () => ({}) } as Response;
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { openai, calls } = makeOpenAIStub();
    instrumentOpenAI(openai, { client });
    await assert.rejects(
      () =>
        openai.chat.completions.create({
          messages: [{ role: "user", content: "hello" }],
          max_tokens: 64,
        }),
      RHEONICValidationError,
    );
    assert.equal(calls.length, 0);
    assert.equal(decisionCalls, 0);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("provider/model validation rejects google call when model is missing", async () => {
  const originalFetch = globalThis.fetch;
  let decisionCalls = 0;
  globalThis.fetch = (async (url: string) => {
    if (url.endsWith("/api/v1/protect/decision")) {
      decisionCalls += 1;
    }
    return { ok: true, status: 202, json: async () => ({}) } as Response;
  }) as typeof fetch;

  try {
    const client = createClient({ ingestKey: "k1", flushIntervalMs: 30_000 });
    const { googleModel, calls } = makeGoogleStub();
    (googleModel as { model?: string; modelName?: string }).model = "";
    (googleModel as { model?: string; modelName?: string }).modelName = "";
    instrumentGoogle(googleModel, { client });
    await assert.rejects(() => googleModel.generateContent("hello"), RHEONICValidationError);
    assert.equal(calls.length, 0);
    assert.equal(decisionCalls, 0);
    client.close();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("provider/model validation rejects missing provider", async () => {
  assert.throws(() => validateProviderModel("", "any-model"), RHEONICValidationError);
});

test("provider/model validation rejects unknown provider", async () => {
  assert.throws(() => validateProviderModel("cohere", "command-r"), RHEONICValidationError);
});
