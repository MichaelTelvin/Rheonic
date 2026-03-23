import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import http from "node:http";
import https from "node:https";
import test from "node:test";

import { requestJson } from "./httpTransport.js";

test("requestJson uses mocked fetch when present", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    ({
      ok: true,
      status: 202,
      json: async () => ({ status: "accepted" }),
    }) as unknown as Response) as unknown as typeof fetch;

  try {
    const response = await requestJson("http://example.test/events", { method: "GET" });
    assert.equal(response.ok, true);
    assert.equal(response.status, 202);
    assert.deepEqual(await response.json(), { status: "accepted" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("requestJson performs native http requests and returns empty payload as object", async () => {
  const originalRequest = http.request;
  const originalFetch = globalThis.fetch;
  const requestSpy = ((options: unknown, callback: (res: EventEmitter & { statusCode?: number }) => void) => {
    const req = new EventEmitter() as EventEmitter & {
      write: (chunk: string) => void;
      end: () => void;
      destroy: (error?: Error) => void;
    };
    req.write = () => {};
    req.destroy = (error?: Error) => {
      if (error) {
        req.emit("error", error);
      }
    };
    req.end = () => {
      void options;
      const res = new EventEmitter() as EventEmitter & { statusCode?: number };
      res.statusCode = 204;
      callback(res);
      res.emit("end");
      req.emit("close");
    };
    return req;
  }) as typeof http.request;
  http.request = requestSpy;
  // Force requestJson down the native http branch instead of Node's built-in fetch.
  Object.defineProperty(globalThis, "fetch", {
    configurable: true,
    value: undefined,
  });

  try {
    const response = await requestJson("http://127.0.0.1:8080/health", { method: "GET" });
    assert.equal(response.status, 204);
    assert.deepEqual(await response.json(), {});
  } finally {
    http.request = originalRequest;
    Object.defineProperty(globalThis, "fetch", {
      configurable: true,
      value: originalFetch,
    });
  }
});

test("requestJson aborts when the signal is already aborted", async () => {
  const controller = new AbortController();
  controller.abort();

  await assert.rejects(
    async () => await requestJson("http://127.0.0.1:1/abort", { method: "GET", signal: controller.signal }),
    (error: unknown) => error instanceof Error && error.name === "AbortError",
  );
});

test("requestJson performs native https requests and writes the request body", async () => {
  const originalRequest = https.request;
  const originalFetch = globalThis.fetch;
  let writtenBody = "";
  const requestSpy = ((options: unknown, callback: (res: EventEmitter & { statusCode?: number }) => void) => {
    const req = new EventEmitter() as EventEmitter & {
      write: (chunk: string) => void;
      end: () => void;
      destroy: (error?: Error) => void;
    };
    req.write = (chunk: string) => {
      writtenBody = chunk;
    };
    req.destroy = (error?: Error) => {
      if (error) {
        req.emit("error", error);
      }
    };
    req.end = () => {
      void options;
      const res = new EventEmitter() as EventEmitter & { statusCode?: number };
      res.statusCode = 200;
      callback(res);
      res.emit("data", JSON.stringify({ ok: true }));
      res.emit("end");
      req.emit("close");
    };
    return req;
  }) as typeof https.request;
  https.request = requestSpy;
  Object.defineProperty(globalThis, "fetch", {
    configurable: true,
    value: undefined,
  });

  try {
    const response = await requestJson("https://example.test/events", { method: "POST", body: "{\"hello\":\"world\"}" });
    assert.equal(writtenBody, "{\"hello\":\"world\"}");
    assert.deepEqual(await response.json(), { ok: true });
  } finally {
    https.request = originalRequest;
    Object.defineProperty(globalThis, "fetch", {
      configurable: true,
      value: originalFetch,
    });
  }
});
