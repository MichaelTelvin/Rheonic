# Protect Mode Spec

## Contract
Protect enforces runtime policy. It does not detect behavioral anomalies.

Protect preflight returns one of:
- `allow`
- `clamp`
- `block`

## Decision Order
1. If cooldown is active, return `block(reason="cooldown_active")`.
2. If request cap is already breached, return `block(reason="req_cap_breach")`.
3. If token cap is already breached, return `block(reason="tok_cap_breach")`.
4. If clamp is enabled and projected token pressure reaches the staged clamp ladder, return `clamp(reason="token_clamp")` with a reduced output-token recommendation.
5. Otherwise return `allow(reason="ok")`.

## Clamp Ladder
- clamp starts at roughly `70%` projected token pressure
- clamp strength increases every `5%` band until `95%`
- each stage reduces the allowed output-token share more aggressively
- the final recommendation is capped both by the active stage and by the actual remaining token budget

## Protect Scope
- no behavioral anomaly detection in preflight
- no incident creation for clamp outcomes
- no ingest-style behavioral evaluation in the preflight path

## Protect Notifications
- `protection.clamp_started`
- `protection.block`

## Protect Incidents
- only one protect-side incident type exists:
  - `block`
- it is opened only on real protect block outcomes caused by:
  - `req_cap_breach`
  - `tok_cap_breach`

## Behavioral Incidents in Protect Projects
Projects in protect mode still ingest events after allowed/clamped requests.
Those ingested events may open behavioral incidents through the same incident manager as observe mode:
- `retry_storm`
- `loop_suspect`
- `token_explosion`
