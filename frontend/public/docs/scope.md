Rheonic — Scope (Current State)

Status: MVP Core is complete. Core platform, protect mode, scheduler jobs, webhook alerts, provider scoping, and docs viewer are implemented.

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
- Always-on SDK preflight (decision endpoint called in observe/protect), with server-side mode deciding enforceability
- Fail-open / fail-closed handling for decision timeout/error
- Protect metrics and health endpoints (project totals with optional provider filter)

Alerts (webhook)
- Project webhook config + test API
- Unified transport hub (shared outbox + RQ worker) for webhook + email delivery
- Webhook dispatch events:
- protect decision warns (`decision.warn`)
- warn incident opens in protect mode (`incident.warn`, non-breach ingest signals after ingest dominance suppression)
- protect decision blocks (`incident.block`)
- incident resolved in protect mode (manual/auto)
- policy-gap first-seen tuples in protect mode (`policy_gap.detected`)
- webhook test (`webhook.test`, mode-independent)
- Delivery failures sourced from `transport_outbox` (`failed` / `dead`) via metrics endpoint

Feedback email
- `POST /api/v1/feedback` is enqueue-only (`202` response)
- Email jobs are processed asynchronously by transport worker
- Current email provider implementation is intentionally unconfigured/stubbed and records deterministic failure code `email_provider_not_configured`

Frontend/docs
- Control Center layout with auth-gated routes
- Dashboard metrics + provider filter
- Dedicated Incidents page with provider/type/status filters
- Docs page + docs/chart viewer and flow charts

========================================
MVP Core Complete
========================================

Core quality and launch gating
- Auth + project isolation enforcement complete and tested
- Ingest/protect/incidents/webhook paths stable under `/api/v1/...`
- Provider-scoped incidents/counters/decisions isolated with no cross-provider bleed
- Coherent docs set (API spec, protect spec, thresholds, diagrams) aligned to runtime behavior
- Backend tests, SDK tests, frontend tests, and existing e2e target green

Operational readiness
- Dashboard/incident UX polished for MVP operator workflows
- Baseline alerting runbook for webhook failures (status visibility and retry behavior)
- Smoke-test scripts/demos for launch validation scenarios implemented (allow, near-cap warn, cap-breach block, retry storm, loop suspect, token explosion, lifecycle)
- Built a production landing page for public launch funnel

========================================
V1 Next Phase (Active)
========================================

Productization and deployment
- Package and deploy backend/frontend to production infrastructure (with environment and secrets management)
- Publish SDK packages to npm and PyPI for external consumption
- Integrate Stripe for billing and subscription lifecycle required for launch
- Finalize release/versioning workflow and launch runbook (rollback + health checks)

========================================
Planned in V2
========================================

Detectors and intelligence
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

Multitenancy evolution
- Org/workspace RBAC multitenancy (roles, workspace scoping, delegated access)
