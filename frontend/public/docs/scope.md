LLMTokenBurnGuard — Scope (Current State)

Status: Core platform, protect mode, scheduler jobs, and webhook alerts are implemented.

========================================
Implemented
========================================

Backend foundation
- FastAPI backend with clean layering
- PostgreSQL + Redis
- RQ workers + scheduler bootstrap
- Health endpoint

Event ingest and realtime
- `POST /api/v1/events`
- Redis rolling 60s counters
- Postgres event persistence
- Idempotency and ingest key rate limiting
- Realtime metrics endpoints

Incident engine
- Baseline snapshots and freeze while incident is open
- Ratio-based anomaly detection
- Dedup window merge for matching open incidents
- Severity escalation with hit cache TTL
- Manual close endpoint
- Auto-close incidents job

Protect mode
- Project-level protect settings (`GET/PUT /api/v1/projects/{project_id}/protect`)
- Decision endpoint (`POST /api/v1/protect/decision`)
- Decision ordering:
- cooldown active -> block
- hard caps (tok/req) -> block
- incident high -> block
- incident medium -> warn
- predictive near-cap -> warn
- else allow
- Predictive snapshot fields in decision response
- Cooldown key set on block reasons (`tok_limit`, `req_limit`, `incident_high`)
- Protect metrics and decision health metrics

SDKs (Node + Python)
- Async fire-and-forget telemetry ingest
- Flush on exit
- OpenAI instrumentation wrappers
- Protect decision enforcement
- SDK-gated preflight (observe mode skips decision endpoint)
- Token estimation runs only in protect mode
- Fail-open / fail-closed handling for decision timeout/error

Dashboard and auth
- User auth (`/api/v1/auth/register`, `/api/v1/auth/login`)
- Project and ingest key management
- Protect settings UI
- Realtime metrics and incidents view
- Protect counters and latency cards

Alerts
- Project webhook config and test API
- High-severity incident webhook dispatch with retries
- Webhook delivery status tracking

Architecture docs and diagrams
- D2 source-of-truth diagrams:
- `docs/architecture/incident_flow.d2`
- `docs/architecture/protect_decision_flow.d2`
- Generated SVG targets under `docs/architecture` and `frontend/public/architecture`

========================================
Remaining / Next
========================================

Detectors and intelligence
- Retry storm detector
- Loop suspect detector
- Token explosion detector

Cost and reconciliation
- Authoritative cost reconciliation pipeline
- Pricing drift warnings
- Budget-triggered policy actions

Operational hardening
- Decision endpoint rate limiting under sustained load
- Expanded background job observability and failure persistence
- Additional e2e scenarios for escalation and auto-close edge cases

Productization
- Public docs/onboarding refinement
- Commercial packaging and billing controls
