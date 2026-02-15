# LLMTokenBurnGuard — Architecture (v1)

## 1) System components

### Client-side
- Python SDK (v1)
- Node SDK (v1)
Both:
- Observe: emit events asynchronously
- Protect: enforce safe actions (opt-in)

### Server-side
- FastAPI Backend
  - Auth, orgs/projects, API keys
  - Event ingest
  - Realtime counters + rollups
  - Anomaly detection + incidents
  - Policy config + evaluation
  - Alert dispatch
- PostgreSQL
  - users, orgs, projects, keys
  - events (raw or semi-raw), rollups
  - incidents, policies, alerts, decision logs
- Redis
  - rolling windows / counters (low latency)
  - incident dedupe state
  - job queue (alerts/rollups)
- Worker
  - RQ or Celery (Redis broker)
  - rollups, retries, cleanup

### Web
- React + Vite + TypeScript
  - Landing/docs
  - Auth app shell
  - Incidents-first dashboard
  - Protect policy settings

## 2) High-level flows

### 2.1 Observe Mode (default)
1. App uses provider SDK via LLMTokenBurnGuard wrapper.
2. Provider returns response (or error).
3. SDK extracts usage (tokens where available), latency, error classification.
4. SDK computes cost from a local + server-synced pricing table.
5. SDK POSTs an Event to `/v1/events` (async, non-blocking).
6. Backend:
   - stores event
   - updates Redis rolling windows
   - runs detectors
   - creates/updates an Incident if triggered
   - triggers alerts (Slack/webhook)
7. Dashboard:
   - reads realtime snapshot (Redis-backed)
   - shows incidents feed and drilldowns

### 2.2 Protect Mode (opt-in)
Protect mode enforcement is client-side, controlled by policy config.

1. SDK loads policy config periodically (e.g., every 10–30s) from `/v1/policy/config`.
2. For each outgoing request, SDK checks:
   - output cap
   - local rate limit counters
   - cooldown state
   - downgrade rule triggers
   - cache fallback eligibility
3. SDK either:
   - allows request (maybe downgraded/capped)
   - or blocks with typed cooldown error (soft)
   - or serves cached response (if available)
4. SDK emits event with guard.action + reason_code.

## 3) “No proxy required” stance
We do not require a drop-in proxy/gateway to deliver value.
(An optional proxy could be a future add-on, but not MVP.)

## 4) Storage model

### Events
- Write: append events to Postgres (batch inserts recommended).
- Realtime: update Redis counters:
  - spend per minute
  - requests per minute
  - retries per minute
  - token sums
- Read:
  - realtime snapshot → Redis
  - history charts → rollups in Postgres

### Rollups (worker)
Generate interval rollups:
- per 1m, 5m, 1h
Groupable by:
- provider, model
- endpoint, feature
- tenant_id

## 5) Detectors (v1, explainable)
All detectors emit:
- incident_type
- severity
- reason_code
- evidence payload

Detectors:
- BURN_RATE_SPIKE:
  - burn_now > burn_baseline * k AND burn_slope positive
- RETRY_STORM:
  - retry_rate > r AND attempt_rate > baseline * m
- LOOP_SUSPECT:
  - repeated job_id or trace_id counts exceed N in window
  - OR prompt_hash repeats exceed N in window
- TOKEN_EXPLOSION:
  - avg input/output tokens now > baseline * p

## 6) Alerts
MVP:
- Slack webhook
- Generic webhook
Later:
- Email, PagerDuty, etc.

## 7) Security
- Project ingest keys (rotate/revoke)
- RBAC: owner/admin/viewer
- Minimal sensitive data storage (no raw prompts by default)