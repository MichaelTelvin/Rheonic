export interface EventRequest {
  endpoint?: string;
  feature?: string;
  input_tokens?: number;
  max_output_tokens?: number;
  protect_decision?: string;
}

export interface EventResponse {
  http_status?: number;
  latency_ms?: number;
  total_tokens?: number;
  error_type?: string;
}

export interface EventPayload {
  ts: string;
  provider: string;
  model: string | null;
  environment: string;
  request: EventRequest;
  response: EventResponse;
}

export interface BuildEventInput {
  provider: string;
  model?: string | null;
  environment?: string;
  ts?: string;
  request?: EventRequest;
  response?: EventResponse;
}

export function buildEvent(input: BuildEventInput): EventPayload {
  return {
    ts: input.ts ?? new Date().toISOString(),
    provider: input.provider,
    model: input.model ?? null,
    environment: input.environment ?? "dev",
    request: input.request ?? {},
    response: input.response ?? {},
  };
}

export class EventBuilder {
  public build(payload: BuildEventInput): EventPayload {
    return buildEvent(payload);
  }
}
