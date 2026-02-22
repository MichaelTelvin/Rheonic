LLMTokenBurnGuard — Scope (Updated MVP Roadmap)

Status: Core MVP Completed  
Target: Complete Operational + Intelligence maturity in next 8 days


========================================
PHASE 0 — FOUNDATION (Completed)
========================================

Infrastructure
- Dockerized backend (FastAPI)
- PostgreSQL + Redis
- RQ workers
- Health endpoint
- Clean architecture layering

Event Ingestion
- POST /api/v1/events
- Redis true sliding window
- Postgres event persistence
- Realtime metrics endpoint
- Burn spike incident detection

Incident Intelligence
- Baseline learning
- Ratio-based spike detection
- Incident deduplication (5-minute merge window)
- Evidence count increment
- Severity escalation (basic)
- Rolling window refactor complete
- Full anomaly test coverage (baseline → spike → escalation)

Backend Hardening
- Idempotency support
- Ingest key rate limiting
- Project ownership checks
- DB indexes:
  - events(project_id, ts)
  - incidents(project_id, status, created_at)
- Proper HTTP status codes
- Retry/backoff for background jobs
- Failed job logging


========================================
PHASE 1 — SDK (Completed MVP)
========================================

Monorepo
- sdk-node
- sdk-python

SDK Capabilities
- Async fire-and-forget ingest
- Flush-on-exit
- OpenAI instrumentation
- Manual capture
- Protect preflight (always-on)
- Predictive near-cap warning
- Hard cap blocking
- Fail-open / fail-closed
- Default-on token estimation
- Production-safe defaults


========================================
PHASE 2 — AUTH & KEY MANAGEMENT (Completed)
========================================

Authentication
- Users table
- Password hashing
- /auth/register
- /auth/login
- JWT middleware
- Route protection

Projects
- Create project
- Ownership enforced
- Project selection UI

Ingest Keys
- Create / rotate / revoke
- Hashed storage
- Key → project mapping
- UI modal flow


========================================
PHASE 3 — OBSERVABILITY DASHBOARD (Completed)
========================================

Metrics
- Requests (60s)
- Tokens (60s)
- Protect decision counters
- Decision latency (p50 / p95)
- Sparkline charts
- Stable timestamp alignment

Incidents
- Open incidents list
- Manual resolve
- Severity badges
- Evidence display

UI
- Dark theme
- Responsive layout
- LLM Control Center header
- Protection status card
- Protect toggle
- Policy editor modal


========================================
PHASE 4 — PROTECT MODE (Completed Core)
========================================

Implemented
- Project-level protect toggle
- Max tokens/min
- Max requests/min
- Predictive near-cap warn
- Hard cap block
- Decision engine (allow / warn / block)
- Snapshot diagnostics
- Dashboard counters
- Node + Python SDK enforcement
- Manual human-tested allow/warn/block


========================================
NEXT 8-DAY EXECUTION PLAN
========================================

We will complete TWO maturity tracks in parallel.

----------------------------------------
TRACK A — Operational Maturity
----------------------------------------

A1. Auto-close incidents
- Auto-resolve incidents when signal drops below threshold for cooldown period
- Configurable cooldown window
- Status transition: open → auto_resolved
- Audit trail preserved

A2. Cooldown logic after block
- Temporary cooldown window after repeated blocks
- Protect state machine behavior:
  - normal
  - cooling_down
  - recovered

A3. Escalation refinement
- Escalate severity on repeated anomaly within time window
- Prevent baseline pollution during open incident

A4. Webhook / alert dispatch
- Trigger on high severity incident creation
- Configurable webhook per project
- Retry with backoff

A5. RQ Scheduler
- Add rq-scheduler service
- Schedule:
  - purge_old_events
  - auto-close job
  - rollup job (if ready)

----------------------------------------
TRACK B — Intelligence Maturity
----------------------------------------

B1. Retry storm detector
- Detect rapid repeated identical requests
- Trigger incident type: retry_storm

B2. Loop suspect detector
- Detect repetitive prompt cycles
- Trigger incident type: loop_suspect

B3. Token explosion detector
- Detect abnormal output/input ratio
- Trigger incident type: token_explosion

B4. Policy gap detection
- Detect new/unrecognized model usage
- Raise UI warning

B5. Improved escalation logic
- Low → Medium → High based on frequency & persistence


========================================
PHASE 5 — COMMERCIALIZATION (After A+B)
========================================

- Billing model
- Subscription tiers
- Stripe integration
- Protect as premium feature
- Usage-based pricing


========================================
CRITICAL TODO (Must Not Be Forgotten)
========================================

Scheduling & Maintenance
- [ ] Integrate rq-scheduler into docker-compose
- [ ] Automate purge_old_events daily
- [ ] Implement auto-close scheduler

Data Retention
- [ ] Finalize retention windows (events vs incidents)
- [ ] Validate production retention automation

Operational Safety
- [ ] Decision endpoint rate limiting at scale
- [ ] Background job observability
- [ ] Dead-letter queue or failure persistence

Product & UX
- [ ] Public documentation site
- [ ] In-app policy explanation tooltips
- [ ] Onboarding flow

Testing
- [ ] Full e2e scenario for auto-close
- [ ] Full e2e scenario for escalation
- [ ] Retry storm unit tests
- [ ] Token explosion unit tests

---

End of updated scope.