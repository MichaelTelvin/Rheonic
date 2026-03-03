# Rheonic API Spec (Current)

All routes are under `/api/v1/...`.

## Auth
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`

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

No severity levels are used in runtime logic.

## Protect settings
- `GET /api/v1/projects/{project_id}/protect`
- `PUT /api/v1/projects/{project_id}/protect`

Fields:
- `protect_enabled` (project mode flag in backend settings; not an SDK wrapper config flag)
- `protect_fail_mode` (`open` | `closed`)
- `apply_clamp`
- `protect_max_req_per_min`
- `protect_max_tok_per_min`
- `protect_decision_timeout_ms`

## Protect decision
- `POST /api/v1/protect/decision`
- `POST /api/v1/protect/decision-timeout`

Decision order in protect mode:
1. cooldown -> `block`
2. req/tok cap breach -> `block`
3. warn signals (`near_cap`, `retry_storm`, `loop_suspect`, `token_explosion`) -> `warn`
4. otherwise `allow`

Protect decision response fields include:
- `apply_clamp_enabled`
- `clamp`:
  - `recommended_max_output_tokens`
  - `applied` (backend recommendation payload; SDK may apply clamp before provider call when enabled)

Observe mode is telemetry-only for enforcement: SDK still calls preflight, and backend mode returns allow (no warn/block enforcement).

## Webhook API
- `GET /api/v1/projects/{project_id}/webhook`
- `PUT /api/v1/projects/{project_id}/webhook`
- `POST /api/v1/projects/{project_id}/webhook/test`

Webhook event types:
- `decision.warn` (protect mode only)
- `incident.warn` (protect mode only; ingest non-breach opens)
- `incident.block` (protect mode only)
- `incident.resolved` (protect mode only)
- `policy_gap.detected` (protect mode only)
- `webhook.test` (mode independent)
