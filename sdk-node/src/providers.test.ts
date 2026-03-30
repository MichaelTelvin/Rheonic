import assert from "node:assert/strict";
import test from "node:test";

import { __setInputTokenEstimatorForTests as setAnthropicEstimatorForTests, instrumentAnthropic } from "./providers/anthropicAdapter.js";
import { __setInputTokenEstimatorForTests as setGoogleEstimatorForTests, instrumentGoogle } from "./providers/googleAdapter.js";
import { __setInputTokenEstimatorForTests as setOpenAIEstimatorForTests, instrumentOpenAI } from "./providers/openaiAdapter.js";

function makeClient(decision: Record<string, unknown>) {
  const captured: unknown[] = [];
  return {
    environment: "dev",
    debugLog: () => {},
    evaluateProtectDecision: async () => decision,
    captureEvent: async (event: unknown) => {
      captured.push(event);
    },
    captured,
  };
}

test("openai adapter clamps max_tokens and captures provider failures", async () => {
  const client = makeClient({
    decision: "warn",
    reason: "near_cap",
    applyClampEnabled: true,
    clamp: { recommended_max_output_tokens: 32, applied: false },
  });
  const openai = {
    chat: {
      completions: {
        create: async (payload: { max_tokens: number; [key: string]: unknown }) => {
          assert.equal(payload.max_tokens, 32);
          const error = new Error("boom") as Error & { statusCode: number };
          error.statusCode = 429;
          throw error;
        },
      },
    },
  };

  instrumentOpenAI(openai, { client: client as any });
  await assert.rejects(async () => await openai.chat.completions.create({ model: "gpt-4o-mini", max_tokens: 128 }));
  assert.equal(client.captured.length, 1);
  assert.equal((client.captured[0] as any).response.http_status, 429);
});

test("anthropic adapter returns original client when messages.create is missing", () => {
  const anthropic = {};
  assert.equal(instrumentAnthropic(anthropic, { client: makeClient({ decision: "allow", reason: "ok" }) as any }), anthropic);
});

test("google adapter injects generation_config clamp into dict payloads", async () => {
  setGoogleEstimatorForTests(() => 77);
  const client = makeClient({
    decision: "warn",
    reason: "near_cap",
    applyClampEnabled: true,
    clamp: { recommended_max_output_tokens: 20, applied: false },
  });
  const google = {
    modelName: "gemini-1.5-pro",
    generateContent: async (...args: unknown[]) => {
      const options = (args[1] ?? {}) as { generationConfig?: { maxOutputTokens?: number } };
      assert.equal(options.generationConfig?.maxOutputTokens, 20);
      return { usageMetadata: { promptTokenCount: 4, candidatesTokenCount: 5 } };
    },
  };

  instrumentGoogle(google, { client: client as any });
  await google.generateContent("hello");
  assert.equal(client.captured.length, 1);
  assert.equal((client.captured[0] as any).response.total_tokens, 9);
  assert.equal((client.captured[0] as any).request.token_explosion_tokens, 77);
  setGoogleEstimatorForTests(null);
});

test("anthropic adapter captures failure status from response object", async () => {
  const client = makeClient({
    decision: "allow",
    reason: "ok",
    applyClampEnabled: false,
  });
  class AnthropicError extends Error {
    response = { status: 429 };
  }
  const anthropic = {
    messages: {
      create: async () => {
        throw new AnthropicError("rate limited");
      },
    },
  };

  instrumentAnthropic(anthropic, { client: client as any });
  await assert.rejects(async () => await (anthropic.messages.create as (...args: unknown[]) => Promise<unknown>)({ model: "claude-3-5-sonnet", max_tokens: 8 }));
  assert.equal((client.captured[0] as any).response.http_status, 429);
});

test("google adapter clamps second-argument generationConfig and preserves lower limits", async () => {
  const client = makeClient({
    decision: "warn",
    reason: "near_cap",
    applyClampEnabled: true,
    clamp: { recommended_max_output_tokens: 20, applied: false },
  });
  const google = {
    modelName: "gemini-1.5-pro",
    generateContent: async (...args: unknown[]) => {
      const options = (args[1] ?? {}) as { generationConfig?: { maxOutputTokens?: number } };
      assert.equal(options.generationConfig?.maxOutputTokens, 10);
      return { response: { usageMetadata: { totalTokenCount: 12 } } };
    },
  };

  instrumentGoogle(google, { client: client as any });
  await google.generateContent("hello", { generationConfig: { maxOutputTokens: 10 } });
  assert.equal((client.captured[0] as any).response.total_tokens, 12);
});

test("google adapter reports failure status from statusCode", async () => {
  const client = makeClient({
    decision: "allow",
    reason: "ok",
    applyClampEnabled: false,
  });
  class GoogleError extends Error {
    statusCode = 503;
  }
  const google = {
    modelName: "gemini-1.5-pro",
    generateContent: async () => {
      throw new GoogleError("backend unavailable");
    },
  };

  instrumentGoogle(google, { client: client as any });
  await assert.rejects(async () => await (google.generateContent as (...args: unknown[]) => Promise<unknown>)("hello"));
  assert.equal((client.captured[0] as any).response.http_status, 503);
});

test("openai adapter clamps max_output_tokens payloads and reads response.status", async () => {
  const client = makeClient({
    decision: "warn",
    reason: "near_cap",
    applyClampEnabled: true,
    clamp: { recommended_max_output_tokens: 24, applied: false },
  });
  const openai = {
    chat: {
      completions: {
        create: async (payload: { max_output_tokens: number; [key: string]: unknown }) => {
          assert.equal(payload.max_output_tokens, 24);
          const error = new Error("boom") as Error & { response: { status: number } };
          error.response = { status: 502 };
          throw error;
        },
      },
    },
  };

  instrumentOpenAI(openai, { client: client as any });
  await assert.rejects(async () => await openai.chat.completions.create({ model: "gpt-4o-mini", max_output_tokens: 64 }));
  assert.equal((client.captured[0] as any).response.http_status, 502);
});

test("anthropic adapter applies clamp when max_tokens is missing and sums token usage", async () => {
  setAnthropicEstimatorForTests(() => 88);
  const client = makeClient({
    decision: "warn",
    reason: "near_cap",
    applyClampEnabled: true,
    clamp: { recommended_max_output_tokens: 11, applied: false },
  });
  const calls: Array<Record<string, unknown>> = [];
  const anthropic = {
    messages: {
      create: async (payload: Record<string, unknown>) => {
        calls.push(payload);
        return { usage: { input_tokens: 5, output_tokens: 8 } };
      },
    },
  };

  instrumentAnthropic(anthropic, { client: client as any });
  await anthropic.messages.create({ model: "claude-3-5-sonnet", messages: [{ role: "user", content: "hello" }] });
  assert.equal(calls[0].max_tokens, 11);
  assert.equal((client.captured[0] as any).response.total_tokens, 13);
  assert.equal((client.captured[0] as any).request.token_explosion_tokens, 88);
  setAnthropicEstimatorForTests(null);
});

test("google adapter returns original object when generateContent is missing", () => {
  const google = { modelName: "gemini-1.5-pro" };
  assert.equal(instrumentGoogle(google, { client: makeClient({ decision: "allow", reason: "ok" }) as any }), google);
});

test("openai adapter returns original object when completions.create is missing", () => {
  const openai = { chat: { completions: {} } };
  assert.equal(instrumentOpenAI(openai, { client: makeClient({ decision: "allow", reason: "ok" }) as any }), openai);
});

test("openai adapter injects recommended max_tokens when no output limit exists", async () => {
  setOpenAIEstimatorForTests(() => 99);
  const client = makeClient({
    decision: "warn",
    reason: "near_cap",
    applyClampEnabled: true,
    clamp: { recommended_max_output_tokens: 13, applied: false },
  });
  const calls: Array<Record<string, unknown>> = [];
  const openai = {
    chat: {
      completions: {
        create: async (payload: Record<string, unknown>) => {
          calls.push(payload);
          return { usage: {} };
        },
      },
    },
  };

  instrumentOpenAI(openai, { client: client as any });
  await openai.chat.completions.create({ model: "gpt-4o-mini", messages: [{ role: "user", content: "hello" }] });
  assert.equal(calls[0].max_tokens, 13);
  assert.equal((client.captured[0] as any).response.total_tokens, undefined);
  assert.equal((client.captured[0] as any).request.token_explosion_tokens, 99);
  setOpenAIEstimatorForTests(null);
});

test("anthropic adapter returns undefined totals and http status from statusCode", async () => {
  const successClient = makeClient({
    decision: "allow",
    reason: "ok",
    applyClampEnabled: false,
  });
  const anthropic = {
    messages: {
      create: async () => ({ model: 123, usage: {} }),
    },
  };

  instrumentAnthropic(anthropic, { client: successClient as any });
  await (anthropic.messages.create as (payload: Record<string, unknown>) => Promise<unknown>)({
    model: "claude-3-5-sonnet",
    max_tokens: 8,
  });
  assert.equal((successClient.captured[0] as any).response.total_tokens, undefined);
  assert.equal((successClient.captured[0] as any).model, "claude-3-5-sonnet");

  const failureClient = makeClient({
    decision: "allow",
    reason: "ok",
    applyClampEnabled: false,
  });
  class AnthropicStatusCodeError extends Error {
    statusCode = 504;
  }
  const failingAnthropic = {
    messages: {
      create: async () => {
        throw new AnthropicStatusCodeError("gateway timeout");
      },
    },
  };

  instrumentAnthropic(failingAnthropic, { client: failureClient as any });
  await assert.rejects(async () =>
    await (failingAnthropic.messages.create as (payload: Record<string, unknown>) => Promise<unknown>)({
      model: "claude-3-5-sonnet",
      max_tokens: 8,
    }));
  assert.equal((failureClient.captured[0] as any).response.http_status, 504);
});

test("google adapter skips clamp when disabled and reads response.status on failures", async () => {
  const successClient = makeClient({
    decision: "warn",
    reason: "near_cap",
    applyClampEnabled: false,
    clamp: { recommended_max_output_tokens: 9, applied: false },
  });
  const successCalls: Array<Record<string, unknown>> = [];
  const google = {
    modelName: "gemini-1.5-pro",
    generateContent: async (payload: Record<string, unknown>) => {
      successCalls.push(payload);
      return {};
    },
  };

  instrumentGoogle(google, { client: successClient as any });
  await google.generateContent({ generationConfig: { maxOutputTokens: 17 } });
  assert.equal((successCalls[0].generationConfig as { maxOutputTokens: number }).maxOutputTokens, 17);
  assert.equal((successClient.captured[0] as any).response.total_tokens, undefined);

  const failureClient = makeClient({
    decision: "allow",
    reason: "ok",
    applyClampEnabled: false,
  });
  class GoogleResponseStatusError extends Error {
    response = { status: 418 };
  }
  const failingGoogle = {
    modelName: "gemini-1.5-pro",
    generateContent: async () => {
      throw new GoogleResponseStatusError("teapot");
    },
  };

  instrumentGoogle(failingGoogle, { client: failureClient as any });
  await assert.rejects(async () =>
    await (failingGoogle.generateContent as (payload: Record<string, unknown>) => Promise<unknown>)({ contents: [] }));
  assert.equal((failureClient.captured[0] as any).response.http_status, 418);
});
