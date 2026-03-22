import assert from "node:assert/strict";
import test from "node:test";

import { EventBuilder, buildEvent } from "./eventBuilder.js";

test("buildEvent fills defaults", () => {
  const payload = buildEvent({ provider: "openai" });
  assert.equal(payload.provider, "openai");
  assert.equal(payload.model, null);
  assert.equal(payload.environment, "dev");
  assert.deepEqual(payload.request, {});
  assert.deepEqual(payload.response, {});
});

test("EventBuilder delegates to buildEvent", () => {
  const builder = new EventBuilder();
  const payload = builder.build({ provider: "anthropic", model: "claude" });
  assert.equal(payload.provider, "anthropic");
  assert.equal(payload.model, "claude");
});
