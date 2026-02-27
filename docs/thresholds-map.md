# Thresholds Map

This map reflects the deterministic anomaly model now used by ingest and protect decisions.

## Rolling 60s Counters
- `rolling_window_seconds`: window used for `requests_60s` and `tokens_60s`.
- `rolling_window_ms`: millisecond form of the same window.
- `rolling_counter_ttl_seconds`: Redis TTL for rolling counter keys.
- Scope: counters are per `(project_id, provider)`.
- Dashboard behavior: totals are aggregated across providers unless provider filter is set.

## Incident Dedup and Lifecycle
- `incident_dedup_window_seconds`: if an open incident with same `(project_id, provider, incident_type)` is inside the window, update it instead of creating a new row.
- `incident_auto_close_seconds`: inactivity cooldown before open incidents are auto-resolved.
- `auto_close_run_interval_seconds`: scheduler cadence for running auto-close.

## Protect Near-Cap Threshold
- `protect_near_cap_factor`: warn ratio used by preflight near-cap checks.
- Near-cap checks:
  - tokens: `tokens_60s + estimated_next_tokens >= tok_cap * protect_near_cap_factor`
  - requests: `requests_60s + 1 >= req_cap * protect_near_cap_factor`
- When it applies:
  - Protect preflight: decision `warn` with webhook `decision.warn`.
  - Ingest (observe/protect): incident signal/logging for `near_cap`.

## Retry Storm Detector
- `retry_storm_window_seconds`: lookback window for failure burst detection.
- `retry_storm_count`: minimum failures in window to trigger.
- Failure criteria: HTTP `>=500`, explicit error status, or error type present.

## Loop Suspect Detector
- `loop_window_seconds`: lookback window for repeated signature detection.
- `loop_count`: minimum matching signature hits to trigger.
- Signature uses provider/model/environment plus stable event characteristics.

## Token Explosion Detector
- `token_explosion_ratio`: ratio threshold against token cap when cap exists.
- `token_explosion_abs`: absolute token threshold when cap-independent trigger is needed.
- Trigger condition: estimate/event tokens exceed ratio threshold or absolute threshold.

## Protect Enforcement
- Hard block conditions (protect mode only):
  - `requests_60s >= protect_max_req_per_min` -> reason `req_cap_breach`
  - `tokens_60s >= protect_max_tok_per_min` -> reason `tok_cap_breach`
- Warn-only signals (protect mode only):
  - `near_cap`
  - `retry_storm`
  - `loop_suspect`
  - `token_explosion`
- `protect_block_cooldown_seconds`: cooldown after block.
- `protect_decision_timeout_ms`: preflight timeout budget.
- `protect_fail_mode`:
  - `open`: allow if decision unavailable
  - `closed`: block if decision unavailable

## Observe Mode Rules
- No preflight call.
- No token estimation for preflight.
- Never returns warn/block action to SDK.
- Ingest still logs incidents (`near_cap`, `retry_storm`, `loop_suspect`, `token_explosion`, `cap_breach` when caps exist).
- No runtime detector/decision webhooks are sent in observe mode.

## Webhook Triggers
- Protect mode only:
  - `decision.warn` for protect decision warn outcomes
  - `incident.warn` for non-breach incident opens from ingest (`retry_storm`, `loop_suspect`, `token_explosion`)
  - `incident.block` for protect decision block outcomes
  - `incident.resolved` for manual and auto resolve
  - `policy_gap.detected` once per first-seen `(project_id, provider, model)`
- Mode independent:
  - `webhook.test`

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
