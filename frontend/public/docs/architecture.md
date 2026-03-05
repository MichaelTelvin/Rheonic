# Rheonic Architecture

## Runtime model
- Scope: `(project_id, provider)` for counters, incidents, and protect decisions.
- Event ingest: `POST /api/v1/events`.
- Protect preflight: `POST /api/v1/protect/decision` (protect mode only).

## Ingest pipeline
1. Persist event.
2. Update rolling 60s counters (`requests_60s`, `tokens_60s`) for `(project, provider)`.
3. Run deterministic detectors:
- `near_cap`
- `retry_storm`
- `loop_suspect`
- `token_explosion`
- `cap_breach` logging from counters/caps
4. Pass signals to `IncidentManager`:
- create/open incident when no recent matching open fingerprint
- otherwise update existing incident (count, last_seen, evidence)
5. Enqueue transport events in shared outbox (`transport_outbox`):
- protect mode decision warns -> `decision.warn`
- protect mode ingest non-breach incident opens -> `incident.warn`
- protect mode decision blocks -> `incident.block`
- protect mode resolution events -> `incident.resolved`
- protect mode policy-gap first-seen tuple -> `policy_gap.detected`
6. RQ transport worker delivers pending outbox rows (`kind=webhook|email`) with retry/backoff and terminal status (`delivered|failed|dead`).
7. Auto-close resolves stale open incidents by inactivity cooldown.

## Protect decision pipeline
1. SDK always calls preflight before provider call.
2. Observe mode returns allow-only behavior (telemetry only).
3. Protect mode preflight reads `(project, provider)` counters and caps.
4. Decision order:
- cooldown active -> `block`
- token/request cap breach -> `block`
- warn-only signals -> `warn`
- else -> `allow`
4. Warn-only signals:
- `near_cap` (predictive)
- `retry_storm`
- `loop_suspect`
- `token_explosion`

## Dashboard metrics behavior
- Endpoints return project totals by default.
- Optional provider filter narrows to a single provider.
- Delivery failures come from `transport_outbox` terminal rows via `GET /api/v1/metrics/delivery-failures`.

## Transport hub behavior
- Shared enqueue API: `TransportService.enqueue(...)` with mandatory `dedupe_key`.
- Webhook and feedback email use the same outbox + RQ worker path.
- Webhook signing, URL safety checks, and HTTP timeout policy are applied in worker delivery.
- Feedback email endpoint is async (`POST /api/v1/feedback` returns `202`) and enqueues `event_type=feedback.submitted`.

## Frontend model
- Dashboard: compact monitoring cards + provider filter.
- Incidents page: provider/type/status filters and incident list.
- Docs page/viewer: architecture diagrams + markdown docs.
