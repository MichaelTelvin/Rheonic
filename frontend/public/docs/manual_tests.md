## Manual Test Scenarios

All API paths remain under `/api/v1/...`.

### 1) Observe mode telemetry only
1. Set project mode to Observe.
2. Run `demo.py` or `demo.ts` with `LLMTBG_DEMO_CASE=steady`.
3. Expected:
- Events ingest succeeds.
- Realtime counters move.
- No preflight decision call.
- Incidents may be logged by deterministic detectors; no protect warn/block action is returned to SDK.

### 2) Protect allow path
1. Set mode Protect and high caps.
2. Run `demo_protect.py` or `demo_protect.ts` with `LLMTBG_SCENARIO=allow`.
3. Expected:
- Decision response `allow`.
- Provider stub is called.

### 3) Protect near-cap warn
1. Set mode Protect with lower token cap.
2. Run protect demo with `LLMTBG_SCENARIO=near_cap`.
3. Expected:
- Decision response `warn` and reason `near_cap`.
- Provider stub is still called.

### 4) Protect cap breach block
1. Set mode Protect and low req/tok cap.
2. Run protect demo with `LLMTBG_SCENARIO=cap_breach`.
3. Expected:
- Decision response `block` with `req_cap_breach` or `tok_cap_breach`.
- Provider stub is not called for blocked step.

### 5) Protect warn-only detector signals
Run protect demo with:
- `LLMTBG_SCENARIO=retry_storm`
- `LLMTBG_SCENARIO=loop_suspect`
- `LLMTBG_SCENARIO=token_explosion`

Expected:
- Decision response `warn` with matching reason.
- Provider stub is still called.

### 6) Incident lifecycle
1. Trigger an incident type in observe or protect mode.
2. Resolve manually from `/api/v1/incidents/{incident_id}/resolve` or wait for auto-close cooldown.
3. Expected:
- Incident status transitions `open` -> `resolved` or `auto_resolved`.
- Resolution webhook event is emitted when webhook is configured.
