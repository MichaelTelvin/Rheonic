# Thresholds Map

This file documents the current behavior after the protect/observe separation refactor.

## Observe: Behavioral Detection
- Behavioral detectors run from ingest in both observe and protect project modes.
- Active incident types:
  - `retry_storm`
  - `loop_suspect`
  - `token_explosion`

### Retry Storm
- `retry_storm_window_seconds`
- `retry_storm_count`

### Loop Suspect
- `loop_window_seconds`
- `loop_count`
- `loop_max_gap_seconds`
- `loop_concurrency_threshold`

### Token Explosion
- signal: `token_explosion_tokens`
- `token_explosion_ratio`
- `token_explosion_abs`
- `token_explosion_growth_ratio`
- `token_explosion_growth_count`
- `token_explosion_growth_min_tokens`
- `token_explosion_concurrency_threshold`

## Protect: Enforcement
- Protect preflight returns only:
  - `allow`
  - `clamp`
  - `block`
- Protect does not evaluate behavioral anomaly detectors anymore.

### Clamp
- internal calculation uses a staged projected-pressure ladder
- runtime settings:
  - `protect_clamp_pressure_thresholds`
  - `protect_clamp_output_ratios`
- default stages:
  - `70%` -> allow up to `90%` of requested output
  - `75%` -> allow up to `80%` of requested output
  - `80%` -> allow up to `70%` of requested output
  - `85%` -> allow up to `55%` of requested output
  - `90%` -> allow up to `40%` of requested output
  - `95%` -> allow up to `25%` of requested output
- final recommendation is still bounded by the real remaining token budget for the request
- clamp decision reason:
  - `token_clamp`

### Block
- hard block conditions:
  - `requests_60s >= protect_max_req_per_min` -> `req_cap_breach`
  - `tokens_60s >= protect_max_tok_per_min` -> `tok_cap_breach`
  - active cooldown -> `cooldown_active`
  - fail-closed fallback -> `fail_closed`
- protect block cooldown:
  - `protect_block_cooldown_seconds`

## Incidents
- Observe/protect ingest opens:
  - `retry_storm`
  - `loop_suspect`
  - `token_explosion`
- Protect block path opens:
  - `block`

## Metrics
- Protect metrics card:
  - `allowed_60m`
  - `clamped_60m`
  - `blocked_60m`

## Notifications
- Behavioral incident opened:
  - `incident.warn`
- Protect clamp started:
  - `protection.clamp_started`
- Protect block:
  - `protection.block`
- Block incident opened:
  - `protection.block`
