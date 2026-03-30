# API Reference

All API routes are served under `/api/v1/...`.

## Authentication
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

Dashboard-authenticated routes use secure `HttpOnly` cookies set by the auth endpoints. Runtime ingest and protect routes use `X-Project-Ingest-Key`.

## Projects
- `GET /api/v1/projects`
- `POST /api/v1/projects`
- `DELETE /api/v1/projects/{project_id}`
- `GET /api/v1/projects/{project_id}/providers`

Projects can be deleted from the product UI as well as through the API.

## Ingest Keys
- `GET /api/v1/projects/{project_id}/keys`
- `POST /api/v1/projects/{project_id}/keys`
- `POST /api/v1/keys/{key_id}/rotate`
- `POST /api/v1/keys/{key_id}/revoke`

## Event Ingest
- `POST /api/v1/events`

Headers:
- `X-Project-Ingest-Key`
- `Idempotency-Key` optional

Typical payload:

```json
{
  "ts": "2026-03-08T10:00:00Z",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "environment": "production",
  "request": {
    "endpoint": "/chat/completions",
    "feature": "assistant",
    "input_tokens": 120
  },
  "response": {
    "output_tokens": 80,
    "total_tokens": 200
  },
  "latency_ms": 320,
  "http_status": 200
}
```

## Metrics
- `GET /api/v1/metrics/realtime?project_id=...&provider=...`
- `GET /api/v1/metrics/protect?project_id=...&provider=...`
- `GET /api/v1/metrics/protect/health?project_id=...&provider=...`
- `GET /api/v1/metrics/delivery-failures?project_id=...&kind=webhook|email`

The `provider` query parameter is optional. Without it, metrics return project totals aggregated across providers.

## Incidents
- `GET /api/v1/incidents?project_id=...&status=open|resolved|all&provider=...`
- `POST /api/v1/incidents/{incident_id}/resolve`

## Protect
- `GET /api/v1/projects/{project_id}/protect`
- `PUT /api/v1/projects/{project_id}/protect`
- `POST /api/v1/protect/decision`

Protect settings include:
- `protect_enabled`
- `protect_fail_mode`
- `apply_clamp`
- `protect_max_req_per_min`
- `protect_max_tok_per_min`

Protect decisions return:
- `decision`
  - values: `allow`, `clamp`, `block`
- `reason`
- `fail_mode`
- `retry_after_seconds`
- `blocked_until`
- `snapshot`
- `apply_clamp_enabled`
- `clamp`

Timeout and unavailable fallback reporting is handled internally between the SDK and backend. It is not part of the normal project integration surface.

## Alerts and Webhooks
- `GET /api/v1/projects/{project_id}/webhook`
- `PUT /api/v1/projects/{project_id}/webhook`
- `POST /api/v1/projects/{project_id}/webhook/test`

## Feedback
- `POST /api/v1/feedback`

The feedback endpoint validates the payload, queues the message for email delivery, and returns `202 Accepted`.
