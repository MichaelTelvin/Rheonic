import assert from "node:assert/strict";
import test from "node:test";

import { instrumentAnthropic, instrumentGoogle } from "./index.js";

function makeClient() {
  return {
    environment: "dev",
    debugLog: () => {},
    evaluateProtectDecision: async () => ({ decision: "allow", reason: "ok" }),
    captureEvent: async () => {},
  };
}

test("index wrappers return original anthropic/google objects without a default client", () => {
  const anthropic = { messages: {} };
  const google = { modelName: "gemini-1.5-pro" };

  assert.equal(instrumentAnthropic(anthropic), anthropic);
  assert.equal(instrumentGoogle(google), google);
});

test("index wrappers honor an explicit client option", () => {
  const anthropic = { messages: {} };
  const google = { modelName: "gemini-1.5-pro" };
  const client = makeClient();

  assert.equal(instrumentAnthropic(anthropic, { client: client as any }), anthropic);
  assert.equal(instrumentGoogle(google, { client: client as any }), google);
});
