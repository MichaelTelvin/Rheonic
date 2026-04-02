import { RHEONICValidationError } from "./providerModelValidation.js";

export interface EventRequest {
  endpoint?: string;
  feature?: string;
  request_fingerprint?: string;
  input_tokens?: number;
  input_tokens_estimate?: number;
  token_explosion_tokens?: number;
  max_output_tokens?: number;
  protect_decision?: string;
  protect_reason?: string;
}

export interface EventResponse {
  http_status?: number;
  latency_ms?: number;
  output_tokens?: number;
  total_tokens?: number;
  error_type?: string;
  error_message?: string;
}

export interface EventPayload {
  ts: string;
  provider: string;
  requested_model: string | null;
  resolved_model: string | null;
  environment: string;
  status?: string;
  request: EventRequest;
  response: EventResponse;
}

export interface BuildEventInput {
  provider: string;
  model?: string | null;
  environment?: string;
  ts?: string;
  status?: string;
  request?: EventRequest;
  response?: EventResponse;
}

export interface InternalEventInput {
  provider: string;
  requested_model?: string | null;
  resolved_model?: string | null;
  environment?: string;
  ts?: string;
  status?: string;
  request?: EventRequest;
  response?: EventResponse;
}

const PUBLIC_EVENT_KEYS = new Set(["provider", "model", "environment", "ts", "status", "request", "response"]);
const INTERNAL_EVENT_KEYS = new Set([
  "provider",
  "requested_model",
  "resolved_model",
  "environment",
  "ts",
  "status",
  "request",
  "response",
]);
const REQUEST_KEYS = new Set([
  "endpoint",
  "feature",
  "request_fingerprint",
  "input_tokens",
  "input_tokens_estimate",
  "token_explosion_tokens",
  "max_output_tokens",
  "protect_decision",
  "protect_reason",
]);
const RESPONSE_KEYS = new Set(["http_status", "latency_ms", "output_tokens", "total_tokens", "error_type", "error_message"]);

function failValidation(message: string): never {
  throw new RHEONICValidationError(message, "event", "", []);
}

function assertPlainObject(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    failValidation(`RHEONIC: ${label} must be an object.`);
  }
  return value as Record<string, unknown>;
}

function assertNoExtraKeys(record: Record<string, unknown>, allowedKeys: Set<string>, label: string): void {
  for (const key of Object.keys(record)) {
    if (!allowedKeys.has(key)) {
      failValidation(`RHEONIC: unexpected ${label} property: ${key}`);
    }
  }
}

function assertOptionalString(value: unknown, label: string): void {
  if (value !== undefined && value !== null && typeof value !== "string") {
    failValidation(`RHEONIC: ${label} must be a string.`);
  }
}

function assertOptionalNumber(value: unknown, label: string): void {
  if (value !== undefined && value !== null && typeof value !== "number") {
    failValidation(`RHEONIC: ${label} must be a number.`);
  }
}

function validateRequestShape(request: unknown): EventRequest {
  const record = assertPlainObject(request, "event.request");
  assertNoExtraKeys(record, REQUEST_KEYS, "event.request");
  assertOptionalString(record.endpoint, "event.request.endpoint");
  assertOptionalString(record.feature, "event.request.feature");
  assertOptionalString(record.request_fingerprint, "event.request.request_fingerprint");
  assertOptionalNumber(record.input_tokens, "event.request.input_tokens");
  assertOptionalNumber(record.input_tokens_estimate, "event.request.input_tokens_estimate");
  assertOptionalNumber(record.token_explosion_tokens, "event.request.token_explosion_tokens");
  assertOptionalNumber(record.max_output_tokens, "event.request.max_output_tokens");
  assertOptionalString(record.protect_decision, "event.request.protect_decision");
  assertOptionalString(record.protect_reason, "event.request.protect_reason");
  return record as EventRequest;
}

function validateResponseShape(response: unknown): EventResponse {
  const record = assertPlainObject(response, "event.response");
  assertNoExtraKeys(record, RESPONSE_KEYS, "event.response");
  assertOptionalNumber(record.http_status, "event.response.http_status");
  assertOptionalNumber(record.latency_ms, "event.response.latency_ms");
  assertOptionalNumber(record.output_tokens, "event.response.output_tokens");
  assertOptionalNumber(record.total_tokens, "event.response.total_tokens");
  assertOptionalString(record.error_type, "event.response.error_type");
  assertOptionalString(record.error_message, "event.response.error_message");
  return record as EventResponse;
}

function validateBuildEventInput(input: BuildEventInput): BuildEventInput {
  const record = assertPlainObject(input, "event");
  assertNoExtraKeys(record, PUBLIC_EVENT_KEYS, "event");
  if (typeof record.provider !== "string" || record.provider.trim().length === 0) {
    failValidation("RHEONIC: event.provider must be a non-empty string.");
  }
  assertOptionalString(record.model, "event.model");
  assertOptionalString(record.environment, "event.environment");
  assertOptionalString(record.ts, "event.ts");
  assertOptionalString(record.status, "event.status");
  if (record.request !== undefined) {
    validateRequestShape(record.request);
  }
  if (record.response !== undefined) {
    validateResponseShape(record.response);
  }
  return input;
}

function validateInternalEventInput(input: InternalEventInput): InternalEventInput {
  const record = assertPlainObject(input, "event");
  assertNoExtraKeys(record, INTERNAL_EVENT_KEYS, "event");
  if (typeof record.provider !== "string" || record.provider.trim().length === 0) {
    failValidation("RHEONIC: event.provider must be a non-empty string.");
  }
  assertOptionalString(record.requested_model, "event.requested_model");
  assertOptionalString(record.resolved_model, "event.resolved_model");
  assertOptionalString(record.environment, "event.environment");
  assertOptionalString(record.ts, "event.ts");
  assertOptionalString(record.status, "event.status");
  if (record.request !== undefined) {
    validateRequestShape(record.request);
  }
  if (record.response !== undefined) {
    validateResponseShape(record.response);
  }
  return input;
}

export function validateEventPayload(input: EventPayload): EventPayload {
  const record = assertPlainObject(input, "event");
  assertNoExtraKeys(record, INTERNAL_EVENT_KEYS, "event");
  for (const requiredKey of ["ts", "provider", "requested_model", "resolved_model", "environment", "request", "response"]) {
    if (!Object.prototype.hasOwnProperty.call(record, requiredKey)) {
      failValidation(`RHEONIC: event.${requiredKey} is required.`);
    }
  }
  if (typeof record.ts !== "string" || record.ts.trim().length === 0) {
    failValidation("RHEONIC: event.ts must be a non-empty string.");
  }
  if (typeof record.provider !== "string" || record.provider.trim().length === 0) {
    failValidation("RHEONIC: event.provider must be a non-empty string.");
  }
  if (typeof record.environment !== "string" || record.environment.trim().length === 0) {
    failValidation("RHEONIC: event.environment must be a non-empty string.");
  }
  assertOptionalString(record.requested_model, "event.requested_model");
  assertOptionalString(record.resolved_model, "event.resolved_model");
  assertOptionalString(record.status, "event.status");
  validateRequestShape(record.request);
  validateResponseShape(record.response);
  return input;
}

export function normalizeEventPayload(input: EventPayload | BuildEventInput): EventPayload {
  const record = assertPlainObject(input, "event");
  const isInternal =
    Object.prototype.hasOwnProperty.call(record, "requested_model")
    || Object.prototype.hasOwnProperty.call(record, "resolved_model");
  if (isInternal) {
    return validateEventPayload(input as EventPayload);
  }
  return buildEvent(input as BuildEventInput);
}

export function buildInternalEvent(input: InternalEventInput): EventPayload {
  validateInternalEventInput(input);
  return {
    ts: input.ts ?? new Date().toISOString(),
    provider: input.provider,
    requested_model: input.requested_model ?? null,
    resolved_model: input.resolved_model ?? null,
    environment: input.environment ?? "dev",
    ...(input.status !== undefined ? { status: input.status } : {}),
    request: input.request ?? {},
    response: input.response ?? {},
  };
}

export function buildEvent(input: BuildEventInput): EventPayload {
  validateBuildEventInput(input);
  return buildInternalEvent({
    provider: input.provider,
    requested_model: input.model ?? null,
    resolved_model: null,
    environment: input.environment,
    ts: input.ts,
    status: input.status,
    request: input.request,
    response: input.response,
  });
}

export class EventBuilder {
  public build(payload: BuildEventInput): EventPayload {
    return buildEvent(payload);
  }
}
