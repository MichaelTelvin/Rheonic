import assert from "node:assert/strict";
import test from "node:test";

import { EventBuilder, buildEvent } from "./eventBuilder.js";

test("buildEvent fills defaults", () => {
  const payload = buildEvent({ provider: "openai" });
  assert.equal(payload.provider, "openai");
  assert.equal(payload.requested_model, null);
  assert.equal(payload.resolved_model, null);
  assert.equal(payload.environment, "dev");
  assert.deepEqual(payload.request, {});
  assert.deepEqual(payload.response, {});
});

test("EventBuilder delegates to buildEvent", () => {
  const builder = new EventBuilder();
  const payload = builder.build({ provider: "anthropic", requested_model: "claude", resolved_model: "claude-v1" });
  assert.equal(payload.provider, "anthropic");
  assert.equal(payload.requested_model, "claude");
  assert.equal(payload.resolved_model, "claude-v1");
});

test("buildEvent preserves request fingerprint", () => {
  const payload = buildEvent({
    provider: "openai",
    request: {
      endpoint: "/chat/completions",
      feature: "loop-fixed-signature",
      request_fingerprint: "fp-loop-fixed",
    },
  });
  assert.equal(payload.request.request_fingerprint, "fp-loop-fixed");
});
