Protect Mode Spec — Always-on Preflight (MVP)

Goal

Add true runtime protection by making the SDK perform a fast preflight decision before every provider call when Protect is enabled for a project.

User-configured (per project)

Stored on projects table (no auto limits):
	•	protect_enabled (bool)
	•	protect_fail_mode = open | closed
	•	protect_max_req_per_min (int, optional)
	•	protect_max_tok_per_min (int, optional)
	•	protect_decision_timeout_ms (int, default 100)
	•	protect_warn_on_incident_severity = medium (warn) / high (block) (MVP hardcode rules ok)

Preflight decision (hot path)

Endpoint:
	•	POST /api/v1/protect/decision
Auth:
	•	X-Project-Ingest-Key header (plaintext key)
Input:

```
{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "feature": "optional",
  "max_output_tokens": 512,
  "input_tokens_estimate": 1200
}
```
Decision outputs:
	•	allow | warn | block
	•	reason: ok | req_limit | tok_limit | incident_medium | incident_high
	•	snapshot: current req/tok 60s + thresholds

Decision rules (ordered):
	1.	If protect disabled → allow
	2.	If requests_60s >= protect_max_req_per_min → block
	3.	If tokens_60s >= protect_max_tok_per_min → block
	4.	If Redis cached incident severity is high → block
	5.	If incident severity is medium → warn
	6.	Else allow

Performance requirements (must)

Decision endpoint must be “Redis-only”:
	•	Resolve ingest key → project_id (use existing mapping; cache in Redis if available)
	•	Read rolling windows from Redis
	•	Read incident severity from Redis (cache written whenever incident changes)
	•	Compare integers, return small JSON
No Postgres writes on decision endpoint.

Telemetry ingest remains async
	•	SDK continues to send telemetry to /api/v1/events as before (fire-and-forget).
	•	Those events keep powering observability and incident creation.

Incident severity cache (Redis)
	•	On incident create/update/resolve, update:
	•	incsev:{project_id} = none|low|medium|high
This is a cache; Postgres remains source of truth.

UI
	•	Project settings panel: Protect toggle + caps + fail mode + timeout
	•	Dashboard header badge: Protect: ON (and optionally Always-on)
	•	Optional small badge for last decision or current mode is NOT required.

SDK behavior

When protect enabled (per project policy returned from backend):
	•	Every provider call:
	•	call /protect/decision with timeout protect_decision_timeout_ms
	•	if allow/warn → proceed provider call
	•	if warn → proceed but tag telemetry + (optional) log warning rate-limited
	•	if block → raise LLMTBGBlockedError, do NOT call provider
	•	On decision failure:
	•	fail-open → proceed provider call
	•	fail-closed → block and raise error

SDK must not “fetch policies per request”. It may:
	•	fetch project settings once at startup or periodically (light polling), OR
	•	infer protect enabled by a config flag passed by user for MVP.
Prefer: poll /protect/mode or /projects/current is optional; simplest is to always preflight and backend returns allow when disabled.
