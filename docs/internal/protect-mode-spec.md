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
- SDK calls `/api/v1/protect/decision` before provider call.
- SDK may send preflight token estimate when available.
- Backend observe mode returns allow-only behavior (no runtime enforcement).
- Provider call proceeds.
- Ingest still records incidents.
- Webhook transport remains incident-oriented:
  - `incident.warn`
  - `incident.resolved`
  - `policy_gap.detected`

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

Protect decisions do not depend on severity or escalation.

## Near-Cap Rule
Protect preflight warns when either condition is met:
- `tokens_60s + estimated_next_tokens >= tok_cap * protect_near_cap_factor`
- `requests_60s + 1 >= req_cap * protect_near_cap_factor`

## Retry-Storm Rule
- Counts failed attempts in the retry-storm window.
- Failure signals are HTTP `>=500`, explicit error status, or error type present.
- Retry intent/state by itself does not count as a failure.

## Token-Explosion Rule
- Counts a dedicated request-side `token_explosion_tokens` signal against the existing ratio and absolute thresholds.
- The SDK computes that signal before the provider call and ingested events persist the same signal, so protect and observe evaluate the same token-explosion pattern.
- Also warns on growth only from values at or above the minimum floor; below that floor, points are ignored as noise.
- `growth_count=2` means two consecutive growth hits across three valid points above that floor. In practice that is `baseline -> spike -> confirmation`, for example `1900 -> 3300 -> 5600`.
- Growth-only detection is suppressed when request volume is high enough to suggest concurrency instead of one step feeding the next.
- Default tuning is intentionally conservative for agentic workflows:
  - ratio `0.9`
  - absolute floor `10000`
  - growth ratio `1.7`
  - growth sequence count `2`
  - growth minimum tokens `1800`
  - concurrency threshold `8`

## Loop-Suspect Rule
- Counts rapid consecutive repeats of the same signature, not scattered frequency across the full window.
- Error events stay eligible because stuck loops often fail while repeating.
- Detection is suppressed when request volume is high enough to suggest concurrency instead of one sequence feeding the next.

## Incidents
Incident types:
- `near_cap`
- `cap_breach`
- `retry_storm`
- `loop_suspect`
- `token_explosion`

Near-cap incidents are fingerprint-split into subtypes:
- `near_cap(req)`
- `near_cap(tok)`
- `near_cap(both)`

Evidence fields include:
- `req_near_cap: bool`
- `tok_near_cap: bool`
- `near_cap_type: "req" | "tok" | "both"`

Incident behavior:
- create on first detection
- dedup+update only while the same detector episode is still active
- when the detector episode window has gone cold, the next trigger opens a fresh incident row
- increment count in evidence
- manual resolve and auto-resolve supported

### Ingest Dominance (strict)
For a single ingested event, incident emission follows this dominance:
1. `cap_breach` dominates all
   - suppresses `near_cap`, `retry_storm`, `loop_suspect`, `token_explosion`
   - resolves only still-active open `near_cap` incidents for the same `(project_id, provider)`
2. `near_cap` dominates behavioral signals when no cap breach exists
   - suppresses `retry_storm`, `loop_suspect`, `token_explosion`
3. Behavioral coexistence is allowed
   - `retry_storm`, `loop_suspect`, `token_explosion` may coexist

For ingest incident emission, near-cap uses observed counters after the current event is counted.
For protect preflight, a live near_cap warn also upserts a visible near_cap incident from the decision snapshot so the warning stays explainable in the dashboard.

## Webhooks
- Observe mode:
  - `incident.warn` on incident open
  - `incident.resolved` on manual/auto resolve
  - `policy_gap.detected` once per new `(project, provider, model)` after the project already has baseline provider/model history
- Protect mode:
  - `protection.warn` on protect warn outcomes (`near_cap`, `retry_storm`, `loop_suspect`, `token_explosion`)
  - `protection.clamp_started` when clamp first begins affecting traffic
  - `protection.block` when Protect prevents traffic:
    - `reason=cap_breach`
    - `reason=cooldown_active`
    - `reason=fail_closed`
  - `incident.resolved` on manual/auto resolve
  - `policy_gap.detected` once per new `(project, provider, model)` after the project already has baseline provider/model history
- Mode independent:
  - `webhook.test` from `/api/v1/projects/{project_id}/webhook/test`
- Delivery path:
  - runtime/API enqueues to shared `transport_outbox` with dedupe key
  - RQ transport worker sends webhook HTTP requests asynchronously
  - retries/backoff and terminal failure state are tracked in outbox rows

## Emails
- Protect mode customer emails use the same core Protect reporting set as webhooks:
  - `protection.warn`
  - `protection.clamp_started`
  - `protection.block`
  - `incident.resolved`
  - `webhook.delivery_failed` when webhook delivery reaches terminal failure
- Observe mode does not send customer email alerts.
- Email does not mirror `policy_gap.detected`.
- Feedback remains a separate internal/system email workflow.

## Metrics
- Realtime: `GET /api/v1/metrics/realtime?project_id=...&provider?`
- Protect counters: `GET /api/v1/metrics/protect?project_id=...&provider?`
- Protect health: `GET /api/v1/metrics/protect/health?project_id=...&provider?`

Schemas stay unchanged; provider filter is optional.
