# Rheonic API Spec (Current)

All routes are under `/api/v1/...`.

## Auth
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

Dashboard/browser auth is cookie-based (`HttpOnly` access + refresh cookies). Access cookies last 60 minutes, refresh/session cookies last 7 days, and refresh is sliding with no idle timeout. Every refresh rotates the refresh token and revokes the prior refresh session server-side; logout revokes the current refresh session server-side and clears browser cookies. Runtime ingest auth remains `X-Project-Ingest-Key`.

## Projects and keys
- `GET /api/v1/projects`
- `POST /api/v1/projects`
- `GET /api/v1/projects/{project_id}/keys`
- `POST /api/v1/projects/{project_id}/keys`
- `POST /api/v1/keys/{key_id}/revoke`
- `POST /api/v1/keys/{key_id}/rotate`
- `GET /api/v1/projects/{project_id}/providers`

## Event ingest
- `POST /api/v1/events`
- Auth: `X-Project-Ingest-Key`
- Core payload fields:
  - `provider`
  - `model`
  - `environment`
  - token usage (`request`/`response` fields)
  - status/error fields

## Metrics
- `GET /api/v1/metrics/realtime?project_id=...&provider?`
- `GET /api/v1/metrics/protect?project_id=...&provider?`
- `GET /api/v1/metrics/protect/health?project_id=...&provider?`
- `GET /api/v1/metrics/delivery-failures?project_id=...&kind=webhook|email`

Provider filter is optional. No schema change when filter is used.

## Incidents
- `GET /api/v1/incidents?project_id=...&status=...&provider?`
- `POST /api/v1/incidents/{incident_id}/resolve`

Incident types:
- `near_cap`
- `cap_breach`
- `retry_storm`
- `loop_suspect`
- `token_explosion`

Severity levels are not part of runtime logic.

## Protect settings
- `GET /api/v1/projects/{project_id}/protect`
- `PUT /api/v1/projects/{project_id}/protect`

Fields:
- `protect_enabled` (project mode flag in backend settings; not an SDK wrapper config flag)
- `protect_fail_mode` (`open` | `closed`)
- `apply_clamp`
- `protect_max_req_per_min`
- `protect_max_tok_per_min`

## Protect decision
- `POST /api/v1/protect/decision`
- `POST /api/v1/protect/decision-timeout`
- `POST /api/v1/protect/decision-unavailable`

Decision order in protect mode:
1. cooldown -> `block`
2. token cap breach -> `block`
3. request cap breach -> `block`
4. warn signals (`near_cap`, `retry_storm`, `loop_suspect`, `token_explosion`) -> `warn`
5. otherwise `allow`

Protect decision response fields include:
- `apply_clamp_enabled`
- `clamp`:
  - `recommended_max_output_tokens`
  - `applied` (backend recommendation payload; SDK may apply clamp before provider call when enabled)

Observe mode is telemetry-only for enforcement: SDK still calls preflight, and backend mode returns allow (no warn/block enforcement).

Canonical protect outcome:
- one request id finalizes exactly one effective outcome
- live decisions and fallback reports converge through the same backend finalization path
- outcome sources are `live`, `timeout_fallback`, or `unavailable_fallback`
- protect counters and `last` are derived from that one finalization path only

## Webhook API
- `GET /api/v1/projects/{project_id}/webhook`
- `PUT /api/v1/projects/{project_id}/webhook`
- `POST /api/v1/projects/{project_id}/webhook/test`

Webhook delivery model:
- Enqueue-only on API/runtime path via `TransportService`.
- Async delivery in RQ worker from `transport_outbox`.
- Source of truth for delivery failures is outbox status (`failed`/`dead`), not project summary fields.

Webhook event types:
- `incident.warn` (observe mode only)
- `protection.warn` (protect mode only)
- `protection.clamp_started` (protect mode only)
- `protection.block` (protect mode only)
- `incident.resolved` (observe + protect)
- `policy_gap.detected` (observe + protect)
- `webhook.test` (mode independent)

Protect email event types:
- `protection.warn`
- `protection.clamp_started`
- `protection.block`
- `incident.resolved`
- `webhook.delivery_failed` (terminal webhook failure escalation when project email alerts are enabled)

## Feedback API
- `POST /api/v1/feedback`
- Behavior: validates payload, enqueues `kind=email` + `event_type=feedback.submitted`, returns `202`.
- Email delivery is processed asynchronously by the transport worker.
- Provider transport is Resend-backed when configured.
