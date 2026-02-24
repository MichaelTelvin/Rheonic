# Protect Mode Spec — Preflight Decision (MVP+)

## Purpose
Protect Mode adds **active runtime enforcement** for LLM usage by using a **preflight decision** before provider calls when protect is enabled in SDK config. It complements observability by preventing cap breaches and reacting to open incident severity.

This spec covers:
- Configuration (user-defined hard caps)
- Decision API behavior (allow/warn/block)
- Predictive blocking (proactive caps)
- SDK enforcement rules (fail-open/fail-closed)
- Caching, audit counters
- Dashboard indicators
- Required tests (unit + E2E)

---

## Definitions

### Project Protect Settings (stored on `projects`)
- `protect_enabled: bool` (default: false)
- `protect_fail_mode: "open" | "closed"` (default: "open")
- `protect_max_req_per_min: int | null` (hard cap; if null -> no req cap)
- `protect_max_tok_per_min: int | null` (hard cap; if null -> no tok cap)
- `protect_decision_timeout_ms: int` (default: 100)

**No auto limits.** All caps are explicitly set by the user.

### Rolling Counters
Counters represent **activity over the last ~60 seconds**:
- `requests_60s`
- `tokens_60s`

These are computed from the system’s rolling window implementation in Redis.

### Provider Scope
Protect runtime state is scoped by **(project_id, provider)**:
- incidents and severity cache are provider-scoped
- rolling counters are provider-scoped
- protect decisions are provider-scoped

Dashboard metric endpoints keep project-level totals by summing across providers, with unchanged response schemas.
Dashboard metrics also support an optional provider filter (`provider=<name>`) for drilldown without changing response shapes.

### Incident Severity Cache (fast path)
Redis key:
- `incsev:{project_id}` = `none|low|medium|high`
Source of truth remains Postgres incidents; Redis is a cache updated on incident changes.

### Incident Auto-Close (cooldown)
- Open incidents are auto-resolved when not seen again for a cooldown window.
- Config: `INCIDENT_AUTO_CLOSE_SECONDS` (default `300`).
- Status transition: `open -> auto_resolved`.
- Protect decision logic only considers currently `open` incidents (auto-resolved incidents are ignored).

### Scheduled Maintenance Jobs
- A dedicated scheduler service (`rq-scheduler`) enqueues recurring maintenance jobs on queue `llmtbg`.
- Recurring jobs:
  - `auto_close_incidents` every `AUTO_CLOSE_RUN_INTERVAL_SECONDS` (default `60`).
  - `purge_old_events` every 24 hours.
- Config distinction:
  - `INCIDENT_AUTO_CLOSE_SECONDS`: cooldown threshold used by auto-close logic.
  - `AUTO_CLOSE_RUN_INTERVAL_SECONDS`: scheduler cadence for enqueueing auto-close runs.

### Project Alerts via Webhook
- Each project can configure one generic webhook destination.
- Trigger: `incident.high` on high-severity incident creation or escalation to high.
- Delivery is asynchronous via RQ with retries.
- UI supports save + test + last delivery status (success/failed, timestamp, short error).

---

## Decision API (Protect-Gated Preflight)

### Endpoint
`POST /api/v1/protect/decision`

### Auth
Header: `X-Project-Ingest-Key: <plaintext key>`

### Request Body (minimal)
```json
{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "feature": "optional-string",
  "max_output_tokens": 512,
  "input_tokens_estimate": 1200
}
```
max_output_tokens is optional.
input_tokens_estimate is SDK default-on best-effort (computed locally); backend accepts omission.

Response Body:

```
{
  "decision": "allow" | "warn" | "block",
  "reason": "ok" | "req_limit" | "tok_limit" | "predictive_near_cap" | "incident_medium" | "incident_high",
  "snapshot": {
    "requests_60s": 0,
    "tokens_60s": 0,
    "threshold_req_60s": null,
    "threshold_tok_60s": null,
    "incident_severity": "none",
    "decision_timeout_ms": 100,
    "predictive": {
      "enabled": true,
      "estimated_next_tokens": 0,
      "would_exceed_tokens_cap": false
    }
  }
}
```
Performance Requirements (hard)

Decision endpoint must be lightning fast:
	•	Redis reads only on the hot path
	•	No Postgres writes in decision endpoint
	•	At most 1 Postgres read (project config) — ideally cached in-process

⸻

Decision Rules (ordered)

Rule 0 — Protect disabled

If protect_enabled == false → allow (even if incident severity is high).

Rule 1 — Hard Request Cap (absolute)

If protect_max_req_per_min != null AND requests_60s >= protect_max_req_per_min → block (reason=req_limit)

Rule 2 — Hard Token Cap (absolute)

If protect_max_tok_per_min != null AND tokens_60s >= protect_max_tok_per_min → block (reason=tok_limit)

Rule 3 — Predictive Near-Cap Warning (proactive; recommended)

If protect_max_tok_per_min != null AND input_tokens_estimate is present:
	•	Compute:
	•	estimated_next_tokens = input_tokens_estimate + (max_output_tokens || 0)
	•	If tokens_60s + estimated_next_tokens reaches near-cap threshold (`protect_near_cap_factor`, default 0.8) → warn (reason=predictive_near_cap)

Predictive signal is warning-only. It does not block by itself.

### SDK Token Estimation

- Default-on in SDK protect preflight payload construction (when protect preflight is enabled in SDK config).
- Local-only tokenization using tokenizer libraries (no network calls).
- SDK computes `input_tokens_estimate` for supported request shapes (for example: chat `messages`, text `prompt`).
- If tokenization fails or request shape is unsupported, SDK skips `input_tokens_estimate` (or sends 0 by convention) with no heuristics.
- No risky guessing (no char-based estimation).
- Performance: encoder instances are cached for fast repeated calls on hot path.

Rule 4 — Incident Severity Influence

Read Redis incsev:{project_id}:
	•	if high → block (reason=incident_high)
	•	if medium → warn (reason=incident_medium)
	•	else → continue

Default

Otherwise → allow (reason=ok)

⸻

SDK Enforcement

Protect-enabled behavior

If SDK protect preflight is enabled, SDK will call `POST /api/v1/protect/decision` before each provider call.

Decision handling:
	•	allow → call provider
	•	warn → call provider; tag telemetry with decision+reason; optional rate-limited log
	•	block → DO NOT call provider; raise LLMTBGBlockedError

Fail behavior

If decision endpoint fails (timeout/5xx/invalid JSON):
	•	fail_mode=open → proceed with provider call
	•	fail_mode=closed → block and raise LLMTBGBlockedError(reason="decision_unavailable")

Timeout:
	•	SDK uses protect_decision_timeout_ms from backend config (cached; refreshed periodically)

⸻

Decision/Protect Audit (recommended)

We do not store every decision in Postgres (too heavy).

We maintain Redis counters for visibility:
	•	pa:{project_id}:warn:60m (INCR, TTL 3600)
	•	pa:{project_id}:block:60m (INCR, TTL 3600)
	•	Optionally pa:{project_id}:last = JSON summary of last decision (short TTL ok)

These counters are updated by the backend decision endpoint.

⸻

Dashboard Requirements (recommended)

Dashboard must make proactive warnings visible.

Header badges
	•	Mode: Observe when protect_enabled=false
	•	Mode: Protect when protect_enabled=true
	•	Small subtext/badge: Caps: Proactive (predictive near-cap warning)
  •  Clarification: Caps: Proactive means predictive logic is enabled; it is effective when `input_tokens_estimate` is present, and `max_output_tokens` improves accuracy.

Protect actions widget (compact)

Show:
	•	Warn (60m): X
	•	Blocked (60m): Y
	•	Optional: Last decision: allow/warn/block

Data comes from a backend endpoint:
GET /api/v1/metrics/protect?project_id=... (JWT auth, ownership enforced)

Provider filter support:
- Dashboard can request provider-scoped metrics with `provider=<name>` on:
  - `GET /api/v1/metrics/realtime`
  - `GET /api/v1/metrics/protect`
  - `GET /api/v1/metrics/protect/health`
- When omitted, backend returns project totals aggregated across providers.

⸻

Tests Required

Backend unit tests

Must cover:
	•	protect disabled -> allow
	•	req limit exceeded -> block (req_limit)
	•	tok limit exceeded -> block (tok_limit)
	•	predictive near-cap -> warn (predictive_near_cap) when input estimate is present and near-cap threshold is reached
	•	predictive does NOT run if max_output_tokens missing; allow unless Rule 2 triggers
	•	incident medium -> warn
	•	incident high -> block
	•	protect disabled + incident high -> allow
	•	snapshot fields present: counters, thresholds, timeout, predictive fields
	•	invalid ingest key -> 401
	•	incsev missing -> treated as none

SDK tests (Node + Python)

Must cover:
	•	decision block -> provider not called; error thrown
	•	decision warn -> provider called; telemetry tagged with decision+reason
	•	decision timeout/500 + fail-open -> provider called
	•	decision timeout/500 + fail-closed -> blocked
	•	decision predictive_near_cap -> warn
	•	messages/prompt request includes local `input_tokens_estimate` in decision payload by default
	•	tokenizer failure path skips estimate without heuristics

End-to-end tests (recommended; required now)

Add E2E harness to run against docker-compose:
	•	Start postgres+redis+backend
	•	Seed: create user/project/key; enable protect; set caps
	•	Spin up a local “provider stub” HTTP server
	•	Run Node SDK call:
	•	allowed call -> provider stub receives request
	•	predictive warned call -> provider stub still receives request
	•	Run Python SDK call with same scenarios
	•	Verify backend Redis protect action counters increment accordingly

E2E must be runnable via make test-e2e.
