1) Observe mode sanity (baseline)

Goal: prove ingest works without protect.

Steps:
	1.	Set Protection OFF in UI.
	2.	Run telemetry demo once (node or python).
	3.	Expected:
	•	Event row created in Postgres
	•	Realtime metrics update
	•	No protect decisions increment (still 0)

(Your node demo currently posts an event with total_tokens: 42.)  ￼

⸻

2) Incident creation from spike (telemetry-only)

Goal: prove your anomaly/incident logic triggers from ingest.

Steps:
	1.	With Protection OFF or ON (doesn’t matter for incident creation), run telemetry demo 5–10 times at low tokens (e.g. 42).
	2.	Modify demo tokens once to a spike (e.g. 420 or higher) and run once.
	3.	Expected:
	•	Incident created (as you saw)
	•	Protect decisions still does not change (because no decision calls happened)

This matches your current observation.

⸻

3) Allow path (protected call)

Goal: verify allow => stub provider called + Allowed counter increments.

Steps (based on node e2e flow):
	1.	Turn Protection ON.
	2.	Set caps very high (so nothing blocks): e.g. req=10000, tok=50000.
	3.	Reset provider stub: POST /reset.
	4.	Run a protected call (not telemetry ingest):
	•	Use the same pattern as protect.e2e.mjs: create client + wrap provider stub + call openai.chat.completions.create(...).  ￼
	5.	Expected:
	•	/protect/decision hit
	•	provider stub /call increments count to 1
	•	Dashboard: Allowed (60m) increments

If you don’t have a manual entrypoint for this yet, this is the missing piece: your demos need a “protected call mode” like the e2e uses.

⸻

4) Warn path (incident-driven)

Goal: incident severity medium => decision warn => provider proceeds.

Steps:
	1.	Ensure Protection ON, fail_mode irrelevant for warn.
	2.	Create a medium incident using telemetry spike.
	3.	Run the protected call once (the wrapped provider stub call).
	4.	Expected:
	•	provider stub count increments
	•	Dashboard: Warned (60m) increments
	•	Telemetry/event tagged decision=warn (if you store it)

Note: if your current spike thresholds classify 10× as “high”, drop spike ratio until it becomes “medium” (e.g. baseline 100, spike 500). Your UI badge is the source of truth.

⸻

5) Block path (incident-driven)

Goal: incident severity high => decision block => provider NOT called.

Steps (exactly like node e2e):
	1.	Protection ON
	2.	Create a high incident by ingesting a huge total_tokens event (e.g. 49000 in e2e).  ￼
	3.	Reset provider stub count
	4.	Run protected call
	5.	Expected:
	•	SDK throws LLMTBGBlockedError
	•	provider stub count stays the same (no new /call)
	•	Dashboard: Blocked (60m) increments

This is the cleanest deterministic block test because it checks both enforcement and “provider not executed.”  ￼

⸻

6) Hard cap block path (deterministic)

Goal: block without incidents, purely from caps.

Steps:
	1.	Protection ON
	2.	Set caps low:
	•	max_tok_per_min = 100
	3.	Do telemetry ingest with total_tokens=200 a couple times quickly (to raise rolling tokens)
	4.	Run protected call
	5.	Expected: block (cap), provider not called, blocked counter increments.

⸻

7) Fail-open vs fail-closed on decision timeout

Goal: show behavior when decision endpoint times out/errors.

Steps:
	1.	Protection ON
	2.	Set decision timeout very low (e.g. 1–5ms) OR temporarily stop backend decision route (simpler: stop backend container briefly)
	3.	With fail-open: protected call should proceed (stub count increments)
	4.	With fail-closed: protected call should block before provider (stub count unchanged)

⸻

8) Predictive near-cap WARN (proactive warning only)

Goal: prove predictive logic warns near cap and never blocks by itself.

Example request:

```bash
curl -sS -X POST "http://localhost:8000/api/v1/protect/decision" \
  -H "Content-Type: application/json" \
  -H "X-Project-Ingest-Key: <INGEST_KEY>" \
  -d '{
    "provider": "openai",
    "model": "gpt-4o-mini",
    "environment": "dev",
    "input_tokens_estimate": 50,
    "max_output_tokens": 200
  }'
```

Expected behavior:
	1.	If rolling tokens are below cap but `tokens_60s + estimate >= cap`, decision returns `warn` with reason `predictive_near_cap`.
	2.	Dashboard `Warned (60m)` increments after protected calls that receive this warn decision.
	3.	Predictive logic does not block. Blocks only happen from hard caps (`req_limit`/`tok_limit`) or high incidents.
