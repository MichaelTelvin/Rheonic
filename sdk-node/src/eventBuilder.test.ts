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
  const payload = builder.build({ provider: "anthropic", model: "claude" });
  assert.equal(payload.provider, "anthropic");
  assert.equal(payload.requested_model, "claude");
  assert.equal(payload.resolved_model, null);
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

test("buildEvent preserves top-level status only", () => {
  const payload = buildEvent({
    provider: "openai",
    status: "error",
    response: {
      http_status: 503,
      error_type: "provider_5xx",
    },
  });

  assert.equal(payload.status, "error");
  assert.equal(payload.response.http_status, 503);
  assert.equal(payload.response.error_type, "provider_5xx");
});

test("buildEvent rejects stale top-level http_status aliases", () => {
  assert.throws(
    () => buildEvent({ provider: "openai", http_status: 503 } as never),
    /unexpected event property: http_status/,
  );
});
