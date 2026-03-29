import { AsyncLocalStorage } from "node:async_hooks";
import { randomUUID } from "node:crypto";

const contextStorage = new AsyncLocalStorage<{ traceId: string; spanId: string }>();

type LogLevel = "debug" | "info" | "warn" | "error";

interface LogEnvelope {
  timestamp: string;
  level: LogLevel;
  service: string;
  env: string;
  trace_id: string;
  span_id: string;
  event: string;
  message: string;
  metadata: Record<string, unknown>;
}

const SENSITIVE_MARKERS = ["api_key", "apikey", "authorization", "cookie", "password", "secret", "token"];
const SERVICE_NAME = "sdk-node";

export function generateTraceId(): string {
  return randomUUID();
}

export function generateSpanId(): string {
  return randomUUID().replace(/-/g, "").slice(0, 16);
}

export function bindTraceContext<T>(traceId: string, spanId: string, fn: () => T): T {
  return contextStorage.run({ traceId, spanId }, fn);
}

export function getTraceId(): string {
  return contextStorage.getStore()?.traceId ?? "";
}

export function getSpanId(): string {
  return contextStorage.getStore()?.spanId ?? "";
}

export function emitLog(params: {
  level: LogLevel;
  event: string;
  message: string;
  metadata?: Record<string, unknown>;
  traceId?: string;
  spanId?: string;
  environment?: string;
}): void {
  const payload: LogEnvelope = {
    timestamp: new Date().toISOString(),
    level: params.level,
    service: SERVICE_NAME,
    env: (
      params.environment ??
      process.env.NODE_ENV ??
      process.env.APP_ENV ??
      process.env.ENVIRONMENT ??
      process.env.ENV ??
      "unknown"
    ).toLowerCase(),
    trace_id: params.traceId ?? getTraceId(),
    span_id: params.spanId ?? getSpanId(),
    event: sanitizeEvent(params.event),
    message: params.message,
    metadata: sanitizeMetadata(params.metadata ?? {}),
  };
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function sanitizeEvent(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
  return normalized || "log";
}

function sanitizeMetadata(value: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, sanitizeValue(entry, key)]));
}

function sanitizeValue(value: unknown, key?: string): unknown {
  if (key && SENSITIVE_MARKERS.some((marker) => key.toLowerCase().includes(marker))) {
    return "[REDACTED]";
  }
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeValue(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([childKey, childValue]) => [
        childKey,
        sanitizeValue(childValue, childKey),
      ]),
    );
  }
  return value ?? null;
}
