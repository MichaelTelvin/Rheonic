# Protect Contract Audit

## Purpose

This audit maps the current Protect request lifecycle across:

- SDK preflight and fallback behavior
- backend authoritative decisioning
- timeout reporting
- Redis-backed dashboard metrics
- incident creation

The goal is to stop patching isolated symptoms and harden one canonical contract.

Status:
- Phase 2 canonical finalization is now implemented.
- This document now tracks what is finished and what remains.

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
4. backend finalizes the request outcome through `ProtectActionStore.finalize_outcome(...)`
5. SDK executes provider call according to returned decision
6. SDK emits event to `/api/v1/events`
7. ingest path may open incidents independently

### Path B: Preflight timeout / unavailable

1. SDK starts preflight
2. preflight times out or fails locally
3. SDK uses local fallback:
   - `allow` if fail mode is `open`
   - `block` if fail mode is `closed`
4. SDK reports timeout or unavailability to the backend fallback endpoint
5. backend finalizes the same request id through `ProtectActionStore.finalize_outcome(...)`
6. if provider call was allowed, SDK emits event to `/api/v1/events`
7. ingest path may still open incidents independently

### Path C: Late preflight response after local timeout

1. SDK times out locally and applies fallback
2. backend may still complete the original `/protect/decision`
3. backend may still complete the original `/protect/decision`
4. request-id reconciliation keeps only the final effective outcome

This is the most fragile path in the current design.

## Current Scenario Matrix

| Scenario | SDK effective behavior | Backend protect metrics | Incident path | Current status |
| --- | --- | --- | --- | --- |
| preflight success + allow | allow provider call | allow counter increments | maybe none | mostly stable |
| preflight success + clamp | allow provider call + clamp metadata | clamped counter increments | may still open ingest-side incident later | mostly stable |
| preflight success + block | block provider call | block counter increments | usually no ingest event | mostly stable |
| timeout + fail-open | allow provider call | increment allow + timeout | ingest may still open incident | covered |
| timeout + fail-closed | block provider call | increment block + timeout | no ingest event | covered |
| timeout, then late clamp | effective outcome should remain fallback result | late clamp must not survive | incident path independent | covered |
| timeout, then late allow, fail-closed | effective outcome should remain block | allow must not survive | no ingest event | covered |
| clamp + apply_clamp off | provider call allowed, no max-token rewrite | clamped counter increments | ingest independent | covered |
| clamp + apply_clamp on | provider call allowed, max-token rewrite | clamped counter increments | ingest independent | covered |
| live block, then cooldown | first call blocks on live decision, repeated same-client call blocks locally, fresh client sees `cooldown_active` live | blocked counter increments only for live backend outcomes; `last.reason` ends as `cooldown_active` | no ingest event | covered |
| backend unavailable at bootstrap | fallback uses cached bootstrap config | unavailable fallback finalizes one outcome | incident path depends on provider call | covered |
| duplicated timeout report | should be idempotent | counters should not double count | none | covered |
| duplicated decision report | should be idempotent per request id | counters should not double count | none | partially covered via finalization |

## Gaps Already Confirmed

### 1. SDK fallback and backend metrics drifted

Previously, timeout fail-open or fail-closed could behave correctly in SDK while dashboard counters reflected a different outcome.

This has now been fixed by canonical request-id finalization.

### 2. Project fail mode was not available to first timed-out SDK request

Previously, a first timed-out request could not honor project `closed` mode because the SDK only learned the real fail mode from a successful preflight.

Fix already applied:

- `GET /api/v1/protect/config`
- SDK bootstrap during warmup

### 3. Protect metrics and incidents are different systems

Protect counters reflect preflight outcomes.
Incidents reflect ingest-time anomaly detection.

This is valid, but the product contract is not explicit enough, so the UI semantics are easy to misread.

### 4. Remaining gap: fallback health is still mostly operator-facing

The backend now distinguishes:

- `live`
- `timeout_fallback`
- `unavailable_fallback`

But the dashboard intentionally rolls these into one user-facing health state instead of exposing raw internals.

## Structural Weaknesses Still Present

### 1. Canonical outcome exists, but coverage is still incomplete

Redis now stores a short-lived normalized outcome per request id and derives counters through one finalization path.

What still remains:

- user-facing health derivation should stay compact and not leak internal source detail

### 2. Timeout and unavailable are now separated internally

SDK and backend now distinguish:

- timeout fallback
- unavailable fallback

The product surface should still roll these up into one compact health signal.

### 3. Idempotency is modeled, but should stay under test

The contract now is:

- one request id ends in exactly one final protect outcome
- repeated fallback reports are ignored
- late live decisions are ignored after fallback finalization

### 4. Dashboard visibility should stay product-focused

The dashboard should show:

- one rolled-up system health state
- not internal fallback/source counters

## Required Contract

Each protect-attempt should have one final normalized outcome:

- `effective_decision`: `allow | clamp | block`
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

Status: complete

### Phase 3: Scenario-matrix tests

Add table-driven tests covering:

- success allow/clamp/block
- timeout fail-open
- timeout fail-closed
- unavailable fail-open
- unavailable fail-closed
- late decision after timeout
- duplicate timeout report
- duplicate decision report
- clamp on/off projected budget pressure
- cooldown active

These tests should assert all of:

- SDK effective behavior
- backend stored outcome
- protect counters
- latest decision
- incident presence/absence where applicable

### Phase 4: Dashboard visibility

Expose and render one compact user-facing health state derived from internal protect health:

- `Healthy`
- `Degraded`
- `Unavailable`

## Immediate Next Implementation Target

1. keep docs/charts/tests aligned with the canonical finalization path
