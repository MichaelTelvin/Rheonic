import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { emitFrontendLog } from "./logger";

describe("emitFrontendLog", () => {
  const consoleDebug = vi.spyOn(console, "debug").mockImplementation(() => undefined);
  const consoleInfo = vi.spyOn(console, "info").mockImplementation(() => undefined);
  const consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);

  beforeEach(() => {
    consoleDebug.mockClear();
    consoleInfo.mockClear();
    consoleWarn.mockClear();
    consoleError.mockClear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("normalizes events and redacts sensitive metadata across objects and arrays", () => {
    emitFrontendLog({
      level: "warn",
      event: "  HTTP Response Failed!  ",
      message: "warned",
      traceId: "trace-1",
      spanId: "span-1",
      metadata: {
        api_key: "secret",
        nested: { authorization: "Bearer xyz", keep: "ok" },
        items: [{ token: "abc" }, { keep: 42 }],
      },
    });

    const payload = JSON.parse(String(consoleWarn.mock.calls[0]?.[0])) as {
      event: string;
      trace_id: string;
      span_id: string;
      metadata: Record<string, unknown>;
    };
    expect(payload.event).toBe("http_response_failed");
    expect(payload.trace_id).toBe("trace-1");
    expect(payload.span_id).toBe("span-1");
    expect(payload.metadata.api_key).toBe("[REDACTED]");
    expect(payload.metadata.nested).toEqual({ authorization: "[REDACTED]", keep: "ok" });
    expect(payload.metadata.items).toEqual([{ token: "[REDACTED]" }, { keep: 42 }]);
  });

  it("routes each log level to the matching console method and defaults nullish values", () => {
    emitFrontendLog({ level: "debug", event: "debug", message: "debugged" });
    emitFrontendLog({ level: "info", event: "info", message: "infoed", metadata: { maybe: undefined } });
    emitFrontendLog({ level: "error", event: "error", message: "errored" });

    expect(consoleDebug).toHaveBeenCalledTimes(1);
    expect(consoleInfo).toHaveBeenCalledTimes(1);
    expect(consoleError).toHaveBeenCalledTimes(1);

    const infoPayload = JSON.parse(String(consoleInfo.mock.calls[0]?.[0])) as {
      trace_id: string;
      span_id: string;
      metadata: Record<string, unknown>;
    };
    expect(infoPayload.trace_id).toBe("");
    expect(infoPayload.span_id).toBe("");
    expect(infoPayload.metadata).toEqual({ maybe: null });
  });
});
