# Protect Mode Spec — Always-on Preflight (MVP+)

## Purpose
Protect Mode adds **active runtime enforcement** for LLM usage by requiring a **preflight decision** before provider calls. It complements observability by preventing cap breaches and reacting to open incident severity.

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

### Incident Severity Cache (fast path)
Redis key:
- `incsev:{project_id}` = `none|low|medium|high`
Source of truth remains Postgres incidents; Redis is a cache updated on incident changes.

### Incident Auto-Close (cooldown)
- Open incidents are auto-resolved when not seen again for a cooldown window.
- Config: `INCIDENT_AUTO_CLOSE_SECONDS` (default `300`).
- Status transition: `open -> auto_resolved`.
- Protect decision logic only considers currently `open` incidents (auto-resolved incidents are ignored).

---

## Decision API (Always-on Preflight)

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
  "reason": "ok" | "req_limit" | "tok_limit" | "tok_predictive" | "incident_medium" | "incident_high",
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

Rule 3 — Predictive Token Cap (proactive; recommended)

If protect_max_tok_per_min != null AND max_output_tokens is present:
	•	Compute:
	•	estimated_next_tokens = max_output_tokens + (input_tokens_estimate || 0)
	•	If tokens_60s + estimated_next_tokens > protect_max_tok_per_min → warn (reason=tok_predictive)

Non-risk rule: If max_output_tokens is missing, do not attempt prediction; allow unless already over cap (Rule 2).

### SDK Token Estimation

- Default-on in SDK preflight payload construction.
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

Always-on behavior

If project protect is enabled, SDK will call POST /protect/decision before each provider call.

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

Dashboard must make “proactive blocking” visible.

Header badges
	•	Mode: Observe when protect_enabled=false
	•	Mode: Protect when protect_enabled=true
	•	Small subtext/badge: Caps: Proactive (since predictive blocking exists when max_output_tokens provided)
  •  Clarification: Caps: Proactive means predictive logic is enabled; it is effective when `max_output_tokens` is present, and `input_tokens_estimate` improves accuracy.

Protect actions widget (compact)

Show:
	•	Warn (60m): X
	•	Blocked (60m): Y
	•	Optional: Last decision: allow/warn/block

Data comes from a backend endpoint:
GET /api/v1/metrics/protect?project_id=... (JWT auth, ownership enforced)

⸻

Tests Required

Backend unit tests

Must cover:
	•	protect disabled -> allow
	•	req limit exceeded -> block (req_limit)
	•	tok limit exceeded -> block (tok_limit)
	•	predictive tok cap -> block (tok_predictive) when max_output_tokens present
	•	predictive does NOT run if max_output_tokens missing; allow unless Rule 2 triggers
	•	incident medium -> warn
	•	incident high -> block
	•	protect disabled + incident high -> allow
	•	snapshot fields present: counters, thresholds, timeout, predictive block fields
	•	invalid ingest key -> 401
	•	incsev missing -> treated as none

SDK tests (Node + Python)

Must cover:
	•	decision block -> provider not called; error thrown
	•	decision warn -> provider called; telemetry tagged with decision+reason
	•	decision timeout/500 + fail-open -> provider called
	•	decision timeout/500 + fail-closed -> blocked
	•	decision tok_predictive -> block
	•	messages/prompt request includes local `input_tokens_estimate` in decision payload by default
	•	tokenizer failure path skips estimate without heuristics

End-to-end tests (recommended; required now)

Add E2E harness to run against docker-compose:
	•	Start postgres+redis+backend
	•	Seed: create user/project/key; enable protect; set caps
	•	Spin up a local “provider stub” HTTP server
	•	Run Node SDK call:
	•	allowed call -> provider stub receives request
	•	predictive blocked call -> provider stub does NOT receive request
	•	Run Python SDK call with same scenarios
	•	Verify backend Redis protect action counters increment accordingly

E2E must be runnable via make test-e2e.
