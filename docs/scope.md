---

## `scope.md` (Codex task list)

```md
# LLMTokenBurnGuard — Scope (Codex Tasks) v1

## Guiding principles
- Do NOT build a proxy.
- Observe mode must be “incident-first”.
- Protect mode is opt-in, deterministic, safe.
- No prompt rewriting.
- Providers: OpenAI, Anthropic, Gemini (Gemini can be v1.1 if needed).
- SDKs: Python + Node (Python first, Node immediately after core is stable).

---

## Milestone 0 — Repo skeleton (Day 1)
- [ ] Create structure:
  - backend/
  - frontend/
  - sdk-python/
  - sdk-node/
  - docs/
- [ ] docker-compose.yml for:
  - postgres
  - redis
  - backend
  - worker
  - frontend
- [ ] .env.example files for each component
- [ ] Formatting & lint:
  - backend: ruff + black
  - sdk-python: ruff + black
  - sdk-node: eslint + prettier
  - frontend: eslint + prettier
- [ ] CI: lint + unit tests

---

## Milestone 1 — Auth + Projects + Billing shell (Week 1)
Backend
- [ ] User auth (email/password) + JWT
- [ ] Org + Project models
- [ ] Project ingest key creation/rotation/revoke
- [ ] RBAC minimal: owner/admin/viewer
- [ ] Stripe placeholders: store customer_id + subscription_status

Frontend
- [ ] Landing placeholder + docs placeholder
- [ ] Auth pages: login/signup
- [ ] App shell: projects list, project settings
- [ ] Display ingest key & install snippet

---

## Milestone 2 — Event ingest + storage + realtime counters (Week 1–2)
Backend
- [ ] POST /v1/events (ingest key auth)
- [ ] Postgres schema for events (start simple)
- [ ] Redis rolling counters (per project):
  - requests/min
  - burn/min
  - retry counts
  - token sums
- [ ] GET /v1/metrics/realtime
- [ ] Pricing table module + versioning

SDK Python (v1)
- [ ] Provide wrapper API:
  - `guard_openai(client, config)`
  - `guard_anthropic(client, config)`
- [ ] Extract token usage and compute cost
- [ ] Async event sender (non-blocking, fire-and-forget)
- [ ] Support tags: endpoint, feature, tenant_id, user_id, job_id, trace_id, env
- [ ] Default prompt_hash behavior (sha256 of normalized content) + allow disable

---

## Milestone 3 — Incidents (anomaly-first) (Week 2)
Backend
- [ ] Incident table/model
- [ ] Detectors:
  - burn spike
  - retry storm
  - loop suspect (job_id/trace_id/prompt_hash)
  - token explosion
- [ ] Incident dedupe + update logic
- [ ] GET /v1/incidents
- [ ] POST /v1/incidents/{id}/close

Frontend
- [ ] Incidents-first dashboard page:
  - open incidents list
  - severity badges
  - scope + evidence
  - drilldown modal/page
- [ ] Realtime snapshot widget (small)

---

## Milestone 4 — Alerts (Week 2–3)
Backend
- [ ] Slack webhook configuration per project
- [ ] Generic webhook configuration per project
- [ ] Alert dispatch worker with retries
- [ ] Trigger on incident open/escalate + budget thresholds

Frontend
- [ ] Alerts settings UI

---

## Milestone 5 — Protect Mode v1 (Week 3–4)
Backend
- [ ] Policy table/model
- [ ] GET /v1/policy/config
- [ ] Budget threshold computation (daily/monthly)
- [ ] Optional decision log table

SDK Python
- [ ] Protect mode toggle
- [ ] Model downgrade (fallback chain per provider)
- [ ] Output token cap enforcement
- [ ] Local rate limiting:
  - project RPM
  - optional tenant RPM
  - behavior: cooldown_block (typed error)
- [ ] Cooldown soft-block:
  - return/raise structured error with retry_after
- [ ] Cached fallback (local in-process TTL cache)
- [ ] Emit guard.action + reason_code in events

Frontend
- [ ] Protect Mode UI:
  - enable toggle
  - budgets
  - fallback chain editor
  - output cap
  - rate limit settings
  - cooldown seconds
  - cache TTL

---

## Milestone 6 — Node SDK (ship right after Python core is stable)
SDK Node (v1)
- [ ] TS package structure + types
- [ ] Wrap OpenAI + Anthropic client calls
- [ ] Same event schema + async sender
- [ ] Same Protect actions (downgrade/cap/rate-limit/cooldown/cache)

---

## Milestone 7 — Gemini support (v1.1 if needed)
- [ ] SDK Python: Gemini wrapper (usage extraction + cost)
- [ ] SDK Node: Gemini wrapper
- [ ] Pricing tables + model mapping updates

---

## Testing (must-have)
Backend
- [ ] Unit tests for each detector using synthetic streams
- [ ] Integration tests for events → incidents creation
SDKs
- [ ] Provider stub tests (no real spend)
- [ ] Protect action deterministic tests
- [ ] Load simulator:
  - normal traffic
  - retry storm
  - loop
  - token explosion

---

## Definition of Done (MVP)
- Auth + project + ingest key
- Python SDK sends events for OpenAI + Anthropic
- Dashboard shows realtime + incidents
- Slack/webhook alerts fire
- Protect mode works (downgrade/cap/rate-limit/cooldown/cache)
- Docker-compose runs full stack locally