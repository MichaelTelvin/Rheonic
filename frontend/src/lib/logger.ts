type LogLevel = "debug" | "info" | "warn" | "error";

const SENSITIVE_MARKERS = ["api_key", "apikey", "authorization", "cookie", "password", "secret", "token"];

export function generateFrontendTraceId(): string {
  return crypto.randomUUID();
}

export function generateFrontendSpanId(): string {
  return crypto.randomUUID().replace(/-/g, "").slice(0, 16);
}

export function emitFrontendLog(params: {
  level: LogLevel;
  event: string;
  message: string;
  metadata?: Record<string, unknown>;
  traceId?: string;
  spanId?: string;
}): void {
  const traceId = params.traceId ?? generateFrontendTraceId();
  const spanId = params.spanId ?? generateFrontendSpanId();
  const payload = {
    timestamp: new Date().toISOString(),
    level: params.level,
    service: "frontend",
    env: ((import.meta as { env?: { MODE?: string } }).env?.MODE ?? "dev").toLowerCase(),
    trace_id: traceId,
    span_id: spanId,
    event: sanitizeEvent(params.event),
    message: params.message,
    metadata: sanitizeMetadata(params.metadata ?? {}),
  };
  console[params.level === "debug" ? "debug" : params.level === "info" ? "info" : params.level === "warn" ? "warn" : "error"](
    JSON.stringify(payload),
  );
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
