# API Spec Snapshot

## Protect Decision
`POST /api/v1/protect/decision`

### Responses
- `allow`
- `clamp`
- `block`

### Reasons
- allow:
  - `ok`
- clamp:
  - `token_clamp`
- block:
  - `req_cap_breach`
  - `tok_cap_breach`
  - `cooldown_active`
  - `fail_closed`

## Incidents
Valid incident types:
- `retry_storm`
- `loop_suspect`
- `token_explosion`
- `block`

Incident types are:
- `retry_storm`
- `loop_suspect`
- `token_explosion`
- `block`

## Notifications
- `incident.warn`
- `incident.block`
- `incident.resolved`
- `protection.clamp_started`
- `protection.block`
- `policy_gap.detected`
