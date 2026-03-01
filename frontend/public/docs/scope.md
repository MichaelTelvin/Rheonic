LLMTokenBurnGuard — Scope (Current State)

Status: Core platform, protect mode, scheduler jobs, webhook alerts, provider scoping, and docs viewer are implemented.

========================================
Implemented
========================================

Backend foundation
- FastAPI backend with layered architecture
- PostgreSQL + Redis
- RQ workers + scheduler bootstrap
- Health endpoint

Auth and tenancy
- User auth (`/api/v1/auth/register`, `/api/v1/auth/login`, refresh flow)
- Project ownership enforcement across project/key/metrics/incidents APIs
- Ingest auth via project ingest key

Event ingest and realtime
- `POST /api/v1/events`
- Redis rolling 60s counters scoped by `(project_id, provider)`
- Postgres event persistence
- Idempotency and ingest key rate limiting
- Realtime metrics endpoints (project totals aggregated across providers; optional provider filter)

Incident engine
- Deterministic detector pipeline (`Detector(s)` -> `Signal` -> `IncidentManager`)
- Incident types: `near_cap`, `cap_breach`, `retry_storm`, `loop_suspect`, `token_explosion`
- Dedup window merge for matching open incidents in `(project_id, provider, incident_type)` scope
- No warmup/ratio/escalation dependency in runtime decisions
- Policy-gap first-seen detection for new `(provider, model)` combinations (record + one-time webhook; no incident)
- Manual resolve endpoint + auto-close incidents job

Protect mode
- Project-level protect settings (`GET/PUT /api/v1/projects/{project_id}/protect`)
- Decision endpoint (`POST /api/v1/protect/decision`)
- Provider-scoped decision inputs/state (counters + cooldown + deterministic warn signals)
- Decision ordering: cooldown -> hard caps (block) -> warn signals (`near_cap`/`retry_storm`/`loop_suspect`/`token_explosion`) -> allow
- SDK-gated preflight (observe skips decision), token estimation in protect mode only
- Fail-open / fail-closed handling for decision timeout/error
- Protect metrics and health endpoints (project totals with optional provider filter)

Alerts (webhook)
- Project webhook config + test API
- Webhook dispatch on:
- protect decision warns (`decision.warn`)
- warn incident opens in protect mode (`incident.warn`, non-breach ingest signals after ingest dominance suppression)
- protect decision blocks (`incident.block`)
- incident resolved in protect mode (manual/auto)
- policy-gap first-seen tuples in protect mode (`policy_gap.detected`)
- webhook test (`webhook.test`, mode-independent)
- Delivery status tracking

Frontend/docs
- Control Center layout with auth-gated routes
- Dashboard metrics + provider filter
- Dedicated Incidents page with provider/type/status filters
- Docs page + docs/chart viewer and flow charts

========================================
V1 Launch Required
========================================

Core quality and launch gating
- Keep auth + project isolation enforcement complete and tested
- Keep ingest/protect/incidents/webhook paths stable under `/api/v1/...`
- Ensure provider-scoped incidents/counters/decisions remain isolated with no cross-provider bleed
- Maintain coherent docs set (API spec, protect spec, thresholds, diagrams) aligned to runtime behavior
- Run and keep green: backend tests, SDK tests, frontend tests, and existing e2e target

Operational readiness
- Final pass on dashboard/incident UX polish for MVP operator workflows
- Baseline alerting runbook for webhook failures (status visibility and retry behavior)
- Smoke-test scripts/demos for launch validation scenarios (allow, near-cap warn, cap-breach block, retry storm, loop suspect, token explosion, lifecycle)

Productization and deployment
- Integrate Stripe for billing and subscription lifecycle required for launch
- Package and deploy backend/frontend to production infrastructure (with environment and secrets management)
- Publish SDK packages to npm and PyPI for external consumption
- Build and deploy a production landing page for public launch funnel
- Finalize release/versioning workflow and launch runbook (rollback + health checks)

========================================
Planned in V2
========================================

Detectors and intelligence
- Retry storm detector heuristics (stub scaffold exists)
- Loop suspect detector heuristics (stub scaffold exists)
- Token explosion detector heuristics (stub scaffold exists)
- Additional anomaly families and detector-specific tuning presets

Providers and policy actions
- Additional provider wrappers beyond current set
- Model downgrade actioning
- Cached response/message strategies tied to policy outcomes

Cost and reconciliation
- Authoritative cost reconciliation pipeline
- Pricing drift warnings
- Budget-triggered policy actions

Aggregation and analytics
- Durable rollups and longer-term aggregation views
- Advanced protect/incident trend analytics

Alerts and channels
- Additional outbound channels (Slack, email, PagerDuty, etc.)
- Channel routing and per-project delivery policies
- Expanded delivery/failure observability

Multitenancy evolution
- Org/workspace RBAC multitenancy (roles, workspace scoping, delegated access)
