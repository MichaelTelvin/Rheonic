LLMTokenBurnGuard — Scope

Phase 0 — Foundation (Completed)

Infrastructure
	•	Dockerized backend (FastAPI)
	•	PostgreSQL + Redis
	•	RQ workers
	•	Health endpoint
	•	Basic project structure (clean architecture layering)

Event Ingestion
	•	POST /api/v1/events
	•	Redis rolling window (true sliding window)
	•	Postgres event persistence
	•	Realtime metrics endpoint
	•	Incident creation (burn spike detection)

Incident Intelligence
	•	Baseline learning
	•	Ratio-based spike detection
	•	Incident deduplication (5-minute merge window)
	•	Evidence count increment
	•	Severity escalation
	•	Rolling window refactor complete
	•	Full anomaly test coverage (baseline → spike → escalation)

Backend Hardening (Completed)
	•	Idempotency support
	•	Ingest key rate limiting
	•	Project ownership checks
	•	Indexes:
	•	events(project_id, ts)
	•	incidents(project_id, status, created_at)
	•	Error handling + proper HTTP status codes
	•	Retry/backoff for background jobs
	•	Failed job logging

⸻

Phase 1 — SDK (Completed MVP)

Monorepo Structure
	•	sdk-node
	•	sdk-python

SDK Capabilities
	•	Async fire-and-forget ingest
	•	Flush-on-exit
	•	OpenAI instrumentation
	•	Manual event capture
	•	Backoff + overflow policy
	•	Production-safe defaults

⸻

Phase 2 — Auth & Key Management (Completed)

Authentication
	•	Users table
	•	Password hashing
	•	/auth/register
	•	/auth/login
	•	JWT auth middleware
	•	Route protection (projects + keys)

Projects
	•	Create project
	•	Project ownership enforced
	•	Project selection in UI

Ingest Keys
	•	Create key
	•	Rotate key
	•	Revoke key
	•	Hashed storage in DB
	•	Key → Project mapping
	•	UI modal flow implemented

⸻

Phase 3 — Observability Dashboard (Completed)

Metrics
	•	Requests (60s)
	•	Tokens (60s)
	•	Sparkline charts
	•	Timestamps (metrics + incidents)

Incidents
	•	Open incidents list
	•	Resolve action
	•	Severity badge
	•	Evidence display

UI
	•	Dark theme
	•	Responsive layout
	•	Stable timestamp alignment
	•	Clean header layout
	•	Login page
	•	JWT session handling

⸻

🔜 Phase 4 — Protect Mode (Next Major Milestone)

Goal: Move from passive observability to active runtime protection.

Protect Mode Objectives

1. Soft Guardrails
	•	Threshold enforcement
	•	Temporary cooldowns
	•	Warning-only mode
	•	Protect mode flag per project

2. Hard Guardrails
	•	Block ingest when limits exceeded
	•	429 responses
	•	Rate-based enforcement
	•	Token cap enforcement

3. Policy System
	•	Project-level policy configuration:
	•	Max tokens / minute
	•	Max requests / minute
	•	Cooldown duration
	•	Escalation rules
	•	Policy stored in DB
	•	Editable via UI

4. Protect Engine (Backend)
	•	Decision engine:
	•	allow
	•	warn
	•	block
	•	Policy evaluation before ingest persistence
	•	Clear audit trail

5. Protect Dashboard UI
	•	Protect mode toggle
	•	Policy editor panel
	•	Real-time protect status
	•	Blocked request counter

⸻

🔜 Phase 5 — Commercialization (After Protect Mode)
	•	Billing model
	•	Subscription tiers
	•	Protect mode as premium feature
	•	Usage-based pricing
	•	Stripe integration
