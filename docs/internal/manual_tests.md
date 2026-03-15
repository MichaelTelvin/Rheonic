## Manual Test Scenarios

All API paths remain under `/api/v1/...`.

### 1) Observe mode telemetry only
1. Set project mode to Observe.
2. Run `tests/e2e/python/demo.py` or `tests/e2e/node/demo.mjs` with `RHEONIC_DEMO_CASE=steady`.
3. Expected:
- Events ingest succeeds.
- Realtime counters move.
- Preflight decision call still occurs before provider call.
- Decision result remains allow-only in observe mode.
- Incidents may be logged by deterministic detectors; no protect warn/block action is returned to SDK.
- No runtime detector/decision webhook should be sent in observe mode.

### 2) Protect allow path
1. Set mode Protect and high caps.
2. Run `tests/e2e/python/demo_protect.py` or `tests/e2e/node/demo_protect.mjs` with `RHEONIC_SCENARIO=allow`.
3. Expected:
- Decision response `allow`.
- Provider stub is called.

### 3) Protect near-cap warn
1. Set mode Protect with lower token cap.
2. Run protect demo with `RHEONIC_SCENARIO=near_cap`.
3. Expected:
- Decision response `warn` and reason `near_cap`.
- Provider stub is still called.

### 3a) Protect near-cap clamp OFF
1. Set mode Protect and disable Auto token clamp in Settings.
2. Run protect demo with `RHEONIC_SCENARIO=near_cap`.
3. Expected:
- Decision response includes `clamp.recommended_max_output_tokens`.
- `clamp.applied=false` in response.
- Provider call proceeds with original `max_output_tokens`.

### 3b) Protect near-cap clamp ON
1. Set mode Protect and enable Auto token clamp in Settings.
2. Run protect demo with `RHEONIC_SCENARIO=near_cap`.
3. Expected:
- Decision response includes `clamp.recommended_max_output_tokens`.
- Demo output shows effective provider request uses clamped max output tokens.
- Provider stub is still called.

### 4) Protect cap breach block
1. Set mode Protect and low req/tok cap.
2. Run protect demo with `RHEONIC_SCENARIO=cap_breach`.
3. Expected:
- Decision response `block` with `req_cap_breach` or `tok_cap_breach`.
- Provider stub is not called for blocked step.

### 4a) Protect request-cap breach block
1. Set mode Protect and set low request cap.
2. Run protect demo with `RHEONIC_SCENARIO=req_cap_breach`.
3. Expected:
- Decision response `block` with `req_cap_breach`.
- Provider stub is not called for blocked step.

### 5) Protect warn-only detector signals
Run protect demo with:
- `RHEONIC_SCENARIO=retry_storm`
- `RHEONIC_SCENARIO=loop_suspect`
- `RHEONIC_SCENARIO=token_explosion`

Expected:
- Decision response `warn` with matching reason.
- Provider stub is still called.
- Webhook event `decision.warn` is dispatched in protect mode.
- No customer email is sent for `decision.warn` alone.

### 6) Incident lifecycle
1. Trigger an incident type in observe or protect mode.
2. Resolve manually from `/api/v1/incidents/{incident_id}/resolve` or wait for auto-close cooldown.
3. Expected:
- Incident status transitions `open` -> `resolved` or `auto_resolved`.
- Resolution transport notifications are emitted only in protect mode:
  - webhook when webhook is configured
  - email when email alerts are enabled

### 7) Protect cooldown after block
1. Run protect demo with `RHEONIC_SCENARIO=cooldown`.
2. Expected:
- First decision blocks on cap breach path.
- Immediate follow-up decision blocks with `cooldown_active`.
- Provider stub remains uncalled while cooldown block is active.
