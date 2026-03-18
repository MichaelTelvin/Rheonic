# Structured Logging

Rheonic runtime services now emit structured JSON logs to stdout only.

## Contract

All runtime logs follow this envelope:

```json
{
  "timestamp": "2026-03-18T09:20:15.120341+00:00",
  "level": "info",
  "service": "backend",
  "env": "staging",
  "trace_id": "f4ac8b6b-6f8d-4f4c-b54f-3c2c2f76a27b",
  "span_id": "9f12db3a1d204f8f",
  "event": "protect_action",
  "message": "Protect decision evaluated",
  "metadata": {
    "project_id": "proj_123",
    "provider": "openai",
    "model": "gpt-4o-mini",
    "environment": "staging-test",
    "decision": "warn",
    "reason": "near_cap",
    "latency_ms": 22
  }
}
```

Required top-level fields:

- `timestamp`
- `level`
- `service`
- `env`
- `trace_id`
- `span_id`
- `event`
- `message`
- `metadata`

## Service Tags

Current runtime service tags:

- `backend`
- `worker`
- `scheduler`
- `sdk-python`
- `sdk-node`
- `frontend`

## Trace Propagation

Rules:

- every incoming backend request gets a `trace_id`
- if `X-Trace-ID` is missing, backend generates a UUID
- backend also generates a `span_id` per request when needed
- response echoes:
  - `X-Trace-ID`
  - `X-Span-ID`
  - `X-Request-ID` (same value as `trace_id` for compatibility)
- outbox jobs inherit the originating `trace_id`
- webhook delivery sends:
  - `X-Trace-ID`
  - `X-Span-ID`
- SDK calls send `X-Trace-ID` on backend requests

## Core Events

High-signal events emitted explicitly in code:

- `http_error`
- `event_ingested`
- `event_duplicate`
- `protect_action`
- `webhook_sent`
- `webhook_failed`
- `email_failed`
- `email_skipped`
- `db_query_slow`
- `db_query_error`
- `outbox_claimed`
- `outbox_delivered`
- `outbox_retry_scheduled`
- `outbox_skipped`
- `worker_started`
- `scheduler_started`
- `scheduler_bootstrap_completed`
- `job_failed`
- `cache_unavailable`
- `sdk_client_initialized`
- `sdk_debug`
- `http_retry`
- `error`

Older call sites that still log through the shared logger without an explicit `event` are still emitted as JSON. Their `event` is derived from the message text. This keeps the codebase consistent during the transition without breaking runtime visibility.

## Error Logging

Structured errors include:

- `trace_id`
- `span_id`
- `error_message`
- `stack_trace`

## Sensitive Data

The shared logger redacts metadata keys containing:

- `api_key`
- `apikey`
- `authorization`
- `cookie`
- `password`
- `secret`
- `token`

## Examples

Protect decision:

```json
{
  "timestamp": "2026-03-18T09:20:15.145102+00:00",
  "level": "info",
  "service": "backend",
  "env": "staging",
  "trace_id": "f4ac8b6b-6f8d-4f4c-b54f-3c2c2f76a27b",
  "span_id": "9f12db3a1d204f8f",
  "event": "protect_action",
  "message": "Protect decision evaluated",
  "metadata": {
    "project_id": "proj_123",
    "provider": "openai",
    "model": "gpt-4o-mini",
    "environment": "staging-test",
    "decision": "warn",
    "reason": "near_cap",
    "latency_ms": 22
  }
}
```

Webhook success:

```json
{
  "timestamp": "2026-03-18T09:20:15.188844+00:00",
  "level": "info",
  "service": "worker",
  "env": "staging",
  "trace_id": "f4ac8b6b-6f8d-4f4c-b54f-3c2c2f76a27b",
  "span_id": "23f74b0ff8f44749",
  "event": "webhook_sent",
  "message": "Webhook delivered",
  "metadata": {
    "outbox_id": "626d2ba8-fe27-42f4-990b-8ececdf35114",
    "event_type": "protection.warn",
    "project_id": "proj_123",
    "destination": "https://example.test/hook",
    "status_code": 200
  }
}
```

Slow query:

```json
{
  "timestamp": "2026-03-18T09:20:15.150201+00:00",
  "level": "warn",
  "service": "backend",
  "env": "staging",
  "trace_id": "f4ac8b6b-6f8d-4f4c-b54f-3c2c2f76a27b",
  "span_id": "9f12db3a1d204f8f",
  "event": "db_query_slow",
  "message": "Slow database query",
  "metadata": {
    "operation": "select",
    "duration_ms": 387.41
  }
}
```

Error:

```json
{
  "timestamp": "2026-03-18T09:20:15.190992+00:00",
  "level": "error",
  "service": "worker",
  "env": "staging",
  "trace_id": "f4ac8b6b-6f8d-4f4c-b54f-3c2c2f76a27b",
  "span_id": "23f74b0ff8f44749",
  "event": "error",
  "message": "Failed to enqueue webhook terminal failure email",
  "metadata": {
    "outbox_id": "626d2ba8-fe27-42f4-990b-8ececdf35114",
    "project_id": "proj_123",
    "event_type": "protection.block",
    "error_message": "email provider not configured",
    "stack_trace": "Traceback (most recent call last): ..."
  }
}
```

## Scope Note

The code snippets shown in frontend quickstart examples still contain `console.log` / `print` text because they are documentation examples, not runtime logging paths.

## Noise Policy

To keep Loki useful:

- routine `http_request` / `http_response` events are not emitted
- database activity is not logged per query
- only `http_error`, `db_query_slow`, and `db_query_error` are logged for those noisy domains
- full payloads, SQL bodies, and query parameters are intentionally omitted
