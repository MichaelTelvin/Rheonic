import assert from "node:assert/strict";
import test from "node:test";

import { instrumentAnthropic } from "./providers/anthropicAdapter.js";
import { instrumentGoogle } from "./providers/googleAdapter.js";
import { instrumentOpenAI } from "./providers/openaiAdapter.js";

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
});
