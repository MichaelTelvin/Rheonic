import assert from "node:assert/strict";
import test from "node:test";

import { bindTraceContext, emitLog, generateSpanId, generateTraceId, getSpanId, getTraceId } from "./logger.js";

test("trace helpers return generated ids and preserve async-local context", () => {
  const traceId = generateTraceId();
  const spanId = generateSpanId();
  assert.equal(spanId.length, 16);

  const result = bindTraceContext(traceId, spanId, () => ({
    traceId: getTraceId(),
    spanId: getSpanId(),
  }));

  assert.equal(result.traceId, traceId);
  assert.equal(result.spanId, spanId);
});

test("emitLog sanitizes events and redacts sensitive metadata", () => {
  const writes: string[] = [];
  const originalWrite = process.stdout.write.bind(process.stdout);
  process.stdout.write = ((chunk: string | Uint8Array) => {
    writes.push(String(chunk));
    return true;
  }) as typeof process.stdout.write;

  try {
    emitLog({
      level: "info",
      event: " HTTP Request Failed! ",
      message: "boom",
      metadata: {
        api_key: "secret",
        nested: { authorization: "secret2" },
        items: [{ password: "hidden" }],
      },
      environment: "Prod",
    });
  } finally {
    process.stdout.write = originalWrite;
  }

  const payload = JSON.parse(writes[0]);
  assert.equal(payload.event, "http_request_failed");
  assert.equal(payload.env, "prod");
  assert.equal(payload.metadata.api_key, "[REDACTED]");
  assert.equal(payload.metadata.nested.authorization, "[REDACTED]");
  assert.equal(payload.metadata.items[0].password, "[REDACTED]");
});
