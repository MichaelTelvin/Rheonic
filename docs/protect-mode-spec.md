# Protect Mode Spec

## Purpose
Protect mode adds preflight enforcement before provider calls. Observe mode remains telemetry-only.

## Scope Model
All runtime state is scoped by `(project_id, provider)`:
- rolling counters
- incidents
- protect decision counters

Dashboard endpoints keep project totals and can optionally filter by provider.

## Modes
### Observe
- SDK does not call `/api/v1/protect/decision`.
- SDK does not run preflight token estimation.
- Provider call proceeds.
- Ingest still records incidents.

### Protect
- SDK calls `/api/v1/protect/decision` before provider call.
- SDK sends provider/model and optional token estimate.
- Decision can be `allow`, `warn`, or `block`.

## Decision Endpoint
- Route: `POST /api/v1/protect/decision`
- Auth: `X-Project-Ingest-Key`

### Decision order (locked)
1. Cooldown active -> `block` (`cooldown_active`)
2. Token cap breached (`tokens_60s >= tok_cap`) -> `block` (`tok_cap_breach`)
3. Request cap breached (`requests_60s >= req_cap`) -> `block` (`req_cap_breach`)
4. Warn-only detector signals (first match):
   - `near_cap`
   - `retry_storm`
   - `loop_suspect`
   - `token_explosion`
5. Otherwise -> `allow` (`ok`)

No severity/escalation dependency exists in protect decisions.

## Near-Cap Rule
Protect preflight warns when either condition is met:
- `tokens_60s + estimated_next_tokens >= tok_cap * protect_near_cap_factor`
- `requests_60s + 1 >= req_cap * protect_near_cap_factor`

## Incidents
Incident types:
- `near_cap`
- `cap_breach`
- `retry_storm`
- `loop_suspect`
- `token_explosion`

Incident behavior:
- create on first detection
- dedup+update within `incident_dedup_window_seconds`
- increment count in evidence
- manual resolve and auto-resolve supported

## Webhooks
- Protect mode:
  - `incident.warn` for warn-type incident detections
  - `incident.block` for block actions / cap breaches
- All modes:
  - `incident.resolved` on manual/auto resolve
- Policy gap:
  - `policy_gap.detected` once per first-seen `(project, provider, model)`

## Metrics
- Realtime: `GET /api/v1/metrics/realtime?project_id=...&provider?`
- Protect counters: `GET /api/v1/metrics/protect?project_id=...&provider?`
- Protect health: `GET /api/v1/metrics/protect/health?project_id=...&provider?`

Schemas stay unchanged; provider filter is optional.
