# Thresholds Map

This map reflects the deterministic anomaly model now used by ingest and protect decisions.

## Rolling 60s Counters
- `rolling_window_seconds`: window used for `requests_60s` and `tokens_60s`.
- `rolling_window_ms`: millisecond form of the same window.
- `rolling_counter_ttl_seconds`: Redis TTL for rolling counter keys.
- Scope: counters are per `(project_id, provider)`.
- Dashboard behavior: totals are aggregated across providers unless provider filter is set.

## Incident Dedup and Lifecycle
- `incident_dedup_window_seconds`: fallback episode window only when a signal does not define its own active episode.
- Incident reuse now follows the signal episode window plus incident `last_seen_at`:
  - same still-active episode -> update existing open row and increment `evidence.count`
  - new separated episode after the detector window cools down -> open a fresh row and emit a fresh `incident.warn`
- Current signal episode windows:
  - `retry_storm`: `retry_storm_window_seconds`
  - `loop_suspect`: `loop_window_seconds`
  - `near_cap`: 60 seconds
  - `token_explosion`: 60 seconds
  - `cap_breach`: 60 seconds
- `incident_auto_close_seconds`: inactivity cooldown before open incidents are auto-resolved. Default: 60 minutes.
- `auto_close_run_interval_seconds`: scheduler cadence for running auto-close.

## Ingest Dominance (per event)
- Dominance level 3: `cap_breach`
  - suppresses: `near_cap`, `retry_storm`, `loop_suspect`, `token_explosion`
  - resolves only recent open `near_cap` incidents for the same `(project_id, provider)` that are still active
- Dominance level 2: `near_cap` (only when no cap breach)
  - suppresses: `retry_storm`, `loop_suspect`, `token_explosion`
- Dominance level 1: `retry_storm`, `loop_suspect`, `token_explosion`
  - coexistence allowed when neither `cap_breach` nor `near_cap` dominates

## Protect Near-Cap Threshold
- `protect_near_cap_factor`: warn ratio used by preflight near-cap checks.
- Protect preflight near-cap checks:
  - tokens: `tokens_60s + estimated_next_tokens >= tok_cap * protect_near_cap_factor`
  - requests: `requests_60s + 1 >= req_cap * protect_near_cap_factor`
- Ingest near-cap checks:
  - tokens: `tokens_60s >= tok_cap * protect_near_cap_factor`
  - requests: `requests_60s >= req_cap * protect_near_cap_factor`
- Near-cap subtypes (same incident type, split fingerprints):
  - `near_cap(tok)` -> `tok_near_cap=true`, `req_near_cap=false`, `near_cap_type="tok"`
  - `near_cap(req)` -> `req_near_cap=true`, `tok_near_cap=false`, `near_cap_type="req"`
  - `near_cap(both)` -> both booleans true, `near_cap_type="both"`
- When it applies:
  - Protect preflight: decision `warn`, visible `near_cap` incident upsert, and Protect reporting event `protection.warn`.
- Ingest (observe/protect): emits `near_cap` incident only when no `cap_breach` dominates that same event. If a later `cap_breach` is reached for the same provider, only still-active open `near_cap` incidents are resolved.

## Retry Storm Detector
- `retry_storm_window_seconds`: lookback window for failure burst detection.
- `retry_storm_count`: minimum failures in window to trigger.
- Failure criteria: HTTP `>=500`, explicit error status, or error type present.
- Retry intent/state alone does not count as a failure for this detector.

## Loop Suspect Detector
- `loop_window_seconds`: lookback window for repeated signature detection.
- `loop_count`: minimum consecutive matching signature steps to trigger.
- `loop_max_gap_seconds`: maximum gap allowed between adjacent repeated steps.
- `loop_concurrency_threshold`: suppress loop detection when request volume suggests concurrency.
- Signature uses provider/model/environment plus stable event characteristics.

## Token Explosion Detector
- Signal: dedicated request-side `token_explosion_tokens`, computed before the provider call and echoed into ingest so protect and observe use the same pattern input.
- `token_explosion_ratio`: ratio threshold against token cap when cap exists. Default `0.9`.
- `token_explosion_abs`: absolute token threshold when cap-independent trigger is needed. Default `10000`.
- `token_explosion_growth_ratio`: sequential growth threshold against the previous matching request-context signal. Default `2.5`.
- `token_explosion_growth_min_tokens`: minimum current request-context size required before growth-only detection is allowed. Default `3000`.
- `token_explosion_concurrency_threshold`: growth-only suppression threshold when request volume suggests concurrency. Default `8`.
- Trigger condition: request-context tokens exceed ratio threshold, absolute threshold, or growth threshold.
- Default tuning is intentionally conservative for agentic workflows:
  - simple agents usually stay well below the absolute floor,
  - RAG flows can grow steadily without being anomalous,
  - growth-only hits should require both a sharp step-up and a meaningfully large current request-context size,
  - parallel tool or worker traffic should not look like one exploding sequence.

## Protect Enforcement
- Hard block conditions (protect mode only):
  - active cooldown -> reason `cooldown_active`
  - `tokens_60s >= protect_max_tok_per_min` -> reason `tok_cap_breach`
  - `requests_60s >= protect_max_req_per_min` -> reason `req_cap_breach`
- Warn-only signals (protect mode only):
  - `near_cap`
  - `retry_storm`
  - `loop_suspect`
  - `token_explosion`
- `protect_block_cooldown_seconds`: cooldown after block.
- `protect_decision_timeout_ms`: backend-only preflight timeout budget set from server config, not project/user settings.
- `protect_fail_mode`:
  - `open`: allow if decision unavailable
  - `closed`: block if decision unavailable

## Observe Mode Rules
- Preflight decision call still runs before provider call.
- SDK may include token estimate when available.
- Never returns warn/block action to SDK.
- Ingest still logs incidents with dominance applied per event:
  - `cap_breach` dominates all
  - else `near_cap` dominates behavioral signals
  - else behavioral signals may coexist
- Observe webhook delivery is incident-oriented:
  - `incident.warn`
  - `incident.resolved`
  - `policy_gap.detected`

## Webhook Triggers
- Observe:
  - `incident.warn` for any incident open
  - `incident.resolved` for manual and auto resolve
  - `policy_gap.detected` once per new `(project_id, provider, model)` after the project already has baseline provider/model history
- Protect:
  - `protection.warn` for protect warning outcomes
  - `protection.clamp_started` when clamp first activates
  - `protection.block` for protect block outcomes
  - `incident.resolved` for manual and auto resolve
  - `policy_gap.detected` once per new `(project_id, provider, model)` after the project already has baseline provider/model history
- Mode independent:
  - `webhook.test`

## Email Triggers
- Protect mode only:
  - `protection.warn`
  - `protection.clamp_started`
  - `protection.block`
  - `incident.resolved`
  - `webhook.delivery_failed` when webhook delivery reaches terminal failure and project email alerts are enabled
- Mode independent:
  - `feedback.submitted` to the internal feedback destination

## Transport Delivery and Retries
- Shared outbox: `transport_outbox` stores webhook/email deliveries and status transitions.
- Webhook retry knobs:
  - `webhook_retry_max_attempts`
  - `webhook_retry_intervals_seconds`
  - `webhook_timeout_connect_seconds`
  - `webhook_timeout_read_seconds`
  - `webhook_timeout_write_seconds`
  - `webhook_timeout_pool_seconds`
- Email retry knobs:
  - `email_retry_max_attempts`
  - `email_retry_intervals_seconds`
  - `email_provider_enabled`
- Failure observability:
  - dashboard delivery failures are derived from outbox rows with status `failed` or `dead`
  - `last_error_code` and `last_error_message` are persisted per outbox delivery

## Tuning Checklist
### Too many warnings
1. Increase `retry_storm_count` or reduce `retry_storm_window_seconds`.
2. Increase `loop_count` or reduce `loop_window_seconds`.
3. Increase `token_explosion_abs` and/or `token_explosion_ratio`.
4. Increase `protect_near_cap_factor` (warn later).

### Missing real incidents
1. Decrease `retry_storm_count`.
2. Decrease `loop_count`.
3. Decrease `token_explosion_abs` and/or `token_explosion_ratio`.
4. Decrease `protect_near_cap_factor` (warn earlier).
