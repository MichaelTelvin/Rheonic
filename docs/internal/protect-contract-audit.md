# Protect Contract Audit

## Purpose

This audit maps the current Protect request lifecycle across:

- SDK preflight and fallback behavior
- backend authoritative decisioning
- timeout reporting
- Redis-backed dashboard metrics
- incident creation

The goal is to stop patching isolated symptoms and harden one canonical contract.

## Current Ownership

### Backend owns

- protect policy settings:
  - `protect_enabled`
  - `protect_fail_mode`
  - `apply_clamp`
  - `protect_max_req_per_min`
  - `protect_max_tok_per_min`
- protect decision timeout default:
  - `Settings().protect_decision_timeout_ms`
- authoritative preflight decision logic
- protect metrics persistence in Redis
- ingest-time anomaly detection and incident creation

### SDK owns

- token estimation
- protect preflight request
- local timeout/unavailable fallback execution
- timeout reporting after failed preflight
- provider-call blocking or allowing in-process

### Dashboard currently sees

- aggregated protect counters from Redis
- latest protect decision snapshot from Redis
- incidents from ingest-time anomaly processing

## Current Request Paths

### Path A: Successful preflight

1. SDK estimates input tokens
2. SDK calls `POST /api/v1/protect/decision`
3. backend evaluates policy in `ProtectService.evaluate_decision(...)`
4. backend writes protect decision counters via `ProtectActionStore.record(...)`
5. SDK executes provider call according to returned decision
6. SDK emits event to `/api/v1/events`
7. ingest path may open incidents independently

### Path B: Preflight timeout / unavailable

1. SDK starts preflight
2. preflight times out or fails locally
3. SDK uses local fallback:
   - `allow` if fail mode is `open`
   - `block` if fail mode is `closed`
4. SDK reports timeout to `POST /api/v1/protect/decision-timeout`
5. backend writes timeout-derived counters via `ProtectActionStore.record_decision_timeout(...)`
6. if provider call was allowed, SDK emits event to `/api/v1/events`
7. ingest path may still open incidents independently

### Path C: Late preflight response after local timeout

1. SDK times out locally and applies fallback
2. backend may still complete the original `/protect/decision`
3. backend may try to write decision counters for that late response
4. timeout report may also write timeout-derived counters
5. request-id reconciliation tries to keep only the final effective outcome

This is the most fragile path in the current design.

## Current Scenario Matrix

| Scenario | SDK effective behavior | Backend protect metrics | Incident path | Current status |
| --- | --- | --- | --- | --- |
| preflight success + allow | allow provider call | allow counter increments | maybe none | mostly stable |
| preflight success + warn | allow provider call + warn | warn counter increments | may also open incident later | mostly stable |
| preflight success + block | block provider call | block counter increments | usually no ingest event | mostly stable |
| timeout + fail-open | allow provider call | should increment allow + timeout | ingest may still open incident | recently fixed |
| timeout + fail-closed | block provider call | should increment block + timeout | no ingest event | recently fixed |
| timeout, then late warn | effective outcome should remain fallback result | late warn must not survive | incident path independent | recently fixed |
| timeout, then late allow, fail-closed | effective outcome should remain block | allow must be removed, block only | no ingest event | recently fixed |
| warn + clamp off | provider call allowed, no max-token rewrite | warn counter increments | ingest independent | needs dedicated end-to-end validation |
| warn + clamp on | provider call allowed, max-token rewrite | warn counter increments | ingest independent | needs dedicated end-to-end validation |
| backend unavailable at bootstrap | fallback uses SDK cached fail mode | metrics depend on timeout/unavailable reporting | incident path depends on provider call | not fully specified |
| duplicated timeout report | should be idempotent | counters should not double count | none | not explicitly tested |
| duplicated decision report | should be idempotent per request id | counters should not double count | none | not explicitly tested |

## Gaps Already Confirmed

### 1. SDK fallback and backend metrics drifted

Previously, timeout fail-open or fail-closed could behave correctly in SDK while dashboard counters reflected a different outcome.

Reason:

- timeout fallback was executed locally in SDK
- backend timeout-report path updated counters separately
- request-id reconciliation was incomplete

### 2. Project fail mode was not available to first timed-out SDK request

Previously, a first timed-out request could not honor project `closed` mode because the SDK only learned the real fail mode from a successful preflight.

Fix already applied:

- `GET /api/v1/protect/config`
- SDK bootstrap during warmup

### 3. Protect metrics and incidents are different systems

Protect counters reflect preflight outcomes.
Incidents reflect ingest-time anomaly detection.

This is valid, but the product contract is not explicit enough, so the UI semantics are easy to misread.

### 4. Timeout is modeled as a secondary request instead of one final outcome record

Current design:

- primary request: `/protect/decision`
- secondary request: `/protect/decision-timeout`

This creates reconciliation complexity and race conditions.

## Structural Weaknesses Still Present

### 1. No canonical per-request protect outcome record

Redis stores counters and a `last` snapshot, but not a first-class normalized outcome object for each request lifecycle.

That means:

- state must be inferred from counters
- timeout reconciliation is patchy
- dashboard semantics depend on derived state

### 2. Timeout and unavailable are conflated in SDK fallback

SDK currently returns:

- `decision_unavailable` for generic failures
- timeout report only for explicit timeout path

The product should probably distinguish:

- `timed_out`
- `backend_unavailable`
- `http_error`
- `invalid_response`

### 3. Idempotency is not explicitly modeled end-to-end

There is request-id reconciliation, but there is no explicit documented contract that says:

- one request id must end in exactly one final protect outcome
- repeated timeout reports are ignored
- repeated late decisions are ignored after finalization

### 4. Dashboard visibility is too narrow

Current dashboard counters show:

- allow/warn/block
- decision timeouts

But they do not clearly show:

- fallback mode usage count
- backend unavailable count
- percentage of requests using local fallback
- whether the latest result was live or fallback-derived

## Required Contract

Each protect-attempt should have one final normalized outcome:

- `effective_decision`: `allow | warn | block`
- `source`: `live | timeout_fallback | unavailable_fallback`
- `reason`
- `fail_mode_used`
- `provider_call_allowed: bool`
- `clamp_applied: bool`
- `incident_expected: bool | unknown`
- `timed_out: bool`
- `request_id`
- `provider`
- `project_id`
- `ts`

Everything else should derive from that record:

- counters
- last decision
- dashboard status
- audit/debug views

## Recommended Hardening Order

### Phase 1: Contract lock-down

1. Write a single scenario table for all protect paths
2. Define expected final normalized outcome for each
3. Define dashboard semantics explicitly:
   - protect decision
   - incident state
   - fallback health

### Phase 2: Canonical outcome persistence

1. Introduce a short-lived Redis record per protect request id
2. Record final normalized outcome once
3. Derive counters from that normalized record update path only
4. Stop having multiple endpoints mutate counters independently without normalization

### Phase 3: Scenario-matrix tests

Add table-driven tests covering:

- success allow/warn/block
- timeout fail-open
- timeout fail-closed
- unavailable fail-open
- unavailable fail-closed
- late decision after timeout
- duplicate timeout report
- duplicate decision report
- clamp on/off near-cap
- cooldown active

These tests should assert all of:

- SDK effective behavior
- backend stored outcome
- protect counters
- latest decision
- incident presence/absence where applicable

### Phase 4: Dashboard visibility

Expose and render:

- `fallback_open_60m`
- `fallback_closed_60m`
- `backend_unavailable_60m`
- `timed_out_60m`
- last protect outcome source

## Immediate Next Implementation Target

Before auth-cookie migration, the next serious backend/SDK hardening task should be:

1. add canonical per-request protect outcome storage
2. route timeout and live decision updates through one finalization path
3. add scenario-matrix tests before changing more UI logic

This is the minimum needed to make fail paths trustworthy.
