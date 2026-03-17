## Manual Test Scenarios

All API paths remain under `/api/v1/...`.

### Demo Run Mode
1. Staging demos run through Doppler config `stgdemo`.
2. Recommended command shape:
- `make demo-stg-python ...`
- `make protect-stg-python ...`
3. The local provider stub at `http://localhost:8099` is optional for protect demos.
- When it is running, you get exact shared provider-call counts.
- When it is absent, protect demos fall back to in-process provider-call tracking instead of failing.

### Protect Scenario Knobs
- `RHEONIC_CAP_BREACH_TOKENS`: token-heavy seed used by `RHEONIC_SCENARIO=cap_breach`
- `RHEONIC_REQ_CAP_BREACH_COUNT`: number of low-token seed events used by `RHEONIC_SCENARIO=req_cap_breach`
- `RHEONIC_CAP_BREACH_REQ_TOKENS`: token size of each request-count seed event
- `RHEONIC_MAX_TOKENS`: max output budget for the final provider call only

`cap_breach` and `req_cap_breach` are intentionally different:
- `cap_breach` simulates a token-cap breach with one large seed event
- `req_cap_breach` simulates a request-cap breach with many small seed events

### 1) Observe mode telemetry only
1. Set project mode to Observe.
2. Run `tests/e2e/python/demo.py` or `tests/e2e/node/demo.mjs` with `RHEONIC_DEMO_CASE=steady`.
3. Expected:
- Events ingest succeeds.
- Realtime counters move.
- Preflight decision call still occurs before provider call.
- Decision result remains allow-only in observe mode.
- Incidents may be logged by deterministic detectors; no protect warn/block action is returned to SDK.
- Runtime webhook transport should be incident-oriented in observe mode.

### 2) Protect allow path
1. Set mode Protect and high caps.
2. Run `tests/e2e/python/demo_protect.py` or `tests/e2e/node/demo_protect.mjs` with `RHEONIC_SCENARIO=allow`.
3. Expected:
- Decision response `allow`.
- Provider call succeeds.

### 3) Protect near-cap warn
1. Set mode Protect with lower token cap.
2. Run protect demo with `RHEONIC_SCENARIO=near_cap`.
3. Expected:
- Decision response `warn` and reason `near_cap`.
- Provider call still succeeds.
- Dashboard shows a visible `near_cap` incident.
- `protection.warn` is delivered over webhook and email once for the protect condition episode.
- If auto clamp is enabled and applied, `protection.clamp_started` is also delivered once for that clamp activation.

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
- Provider call still succeeds.

### 4) Protect cap breach block
1. Set mode Protect and low req/tok cap.
2. Run protect demo with `RHEONIC_SCENARIO=cap_breach`.
3. Expected:
- Decision response `block` with `req_cap_breach` or `tok_cap_breach`.
- Provider call is not executed for blocked step.
- `protection.block` is delivered with `reason=cap_breach`.

### 4a) Protect request-cap breach block
1. Set mode Protect and set low request cap.
2. Run protect demo with `RHEONIC_SCENARIO=req_cap_breach`.
3. Expected:
- Decision response `block` with `req_cap_breach`.
- Provider call is not executed for blocked step.
- Dashboard request counters move from the seed events.
- Token counters move only by `RHEONIC_CAP_BREACH_REQ_TOKENS * event_count`, not by `RHEONIC_MAX_TOKENS`.
- `protection.block` is delivered with `reason=cap_breach` and `detail_reason=req_cap_breach`.

### 5) Protect warn-only detector signals
Run protect demo with:
- `RHEONIC_SCENARIO=retry_storm`
- `RHEONIC_SCENARIO=loop_suspect`
- `RHEONIC_SCENARIO=token_explosion`

Expected:
- Decision response `warn` with matching reason.
- Provider call still succeeds.
- `protection.warn` is dispatched in protect mode.
- The same `protection.warn` semantic is delivered to email when email alerts are enabled.

### 5a) Webhook test should not create delivery-failure alerts
1. Save a failing webhook URL in Alerts.
2. Click `Test webhook`.
3. Expected:
- Alerts page shows the test result.
- Dashboard does not show the webhook delivery issues banner because test sends are excluded.
- No `webhook.delivery_failed` customer email is sent for the test failure alone.

### 5b) Webhook transport matrix
Run these protect scenarios with webhook enabled and inspect the receiver output:
- `RHEONIC_SCENARIO=near_cap`
- `RHEONIC_SCENARIO=retry_storm`
- `RHEONIC_SCENARIO=loop_suspect`
- `RHEONIC_SCENARIO=token_explosion`
- `RHEONIC_SCENARIO=cap_breach`
- `RHEONIC_SCENARIO=cooldown`

Expected:
- `near_cap` -> `protection.warn`
- `retry_storm` -> `protection.warn`
- `loop_suspect` -> `protection.warn`
- `token_explosion` -> `protection.warn`
- `cap_breach` -> `protection.block` with `reason=cap_breach`
- `cooldown` -> first `protection.block` with `reason=cap_breach`, then one `protection.block` with `reason=cooldown_active`

Then resolve the open incident.

Expected:
- `incident.resolved` is delivered over webhook.

Policy-gap check:
1. Trigger a first-seen `(project, provider, model)` tuple in protect mode.
2. Expected:
- `policy_gap.detected` is delivered over webhook.
- no dedicated in-app notification is expected.

### 6) Incident lifecycle
1. Trigger an incident type in observe or protect mode.
2. Resolve manually from `/api/v1/incidents/{incident_id}/resolve` or wait for auto-close cooldown.
3. Expected:
- Incident status transitions `open` -> `resolved` or `auto_resolved`.
- `incident.resolved` webhook is emitted in both modes when webhook is configured.
- `incident.resolved` email is emitted only in protect mode when email alerts are enabled.

### 7) Protect cooldown after block
1. Run protect demo with `RHEONIC_SCENARIO=cooldown`.
2. Expected:
- First decision blocks on cap breach path.
- Immediate follow-up decision blocks with `cooldown_active`.
- Provider call remains unexecuted while cooldown block is active.
- `protection.block(reason=cooldown_active)` is delivered once for the cooldown block episode, not on every repeated blocked request.

### Observe webhook transport matrix
Run these observe scenarios with webhook enabled and inspect the receiver output:
- `RHEONIC_DEMO_CASE=near_cap`
- `RHEONIC_DEMO_CASE=retry_storm`
- `RHEONIC_DEMO_CASE=loop_suspect`
- `RHEONIC_DEMO_CASE=token_explosion`
- `RHEONIC_DEMO_CASE=cap_breach`

Expected:
- each incident open emits `incident.warn`
- `incident_type` distinguishes `near_cap`, `cap_breach`, `retry_storm`, `loop_suspect`, `token_explosion`
- no `protection.*` events are emitted in observe mode
