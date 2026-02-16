LLMTokenBurnGuard — Scope

Overview

LLMTokenBurnGuard is a realtime observability and guardrail platform for LLM API usage.

It monitors:
	•	Token burn
	•	Request rates
	•	Rolling 60s usage windows
	•	Incidents (burn spikes / request storms)

It provides:
	•	Realtime dashboard
	•	Incident tracking
	•	Resolve workflow
	•	Clean dark SaaS UI
	•	True rolling window implementation (Redis ZSET)

⸻

Milestone 0 — Foundation & Infrastructure ✅ DONE

Backend
	•	FastAPI project skeleton
	•	Layered architecture (API → Service → Repository → Infrastructure)
	•	SQLAlchemy integration
	•	Postgres containerized
	•	Redis containerized
	•	RQ worker container
	•	Docker Compose working end-to-end
	•	Health endpoint

Frontend
	•	Vite + React + TypeScript setup
	•	Dockerized frontend
	•	Dev proxy via Vite for backend
	•	CORS resolved properly

⸻

Milestone 1 — Events Ingest + Realtime Metrics ✅ DONE

Backend
	•	POST /api/v1/events
	•	Persist event to Postgres
	•	Redis true rolling window (ZSET-based, last 60 seconds)
	•	GET /api/v1/metrics/realtime
	•	Unit tests for rolling window logic

Realtime Semantics
	•	ZSET per project for:
	•	requests
	•	tokens
	•	Score = timestamp (ms)
	•	Trim older than 60 seconds
	•	True rolling window (not TTL bucket)

⸻

Milestone 2 — Incident Engine (Backend) ✅ DONE

Incident Triggering
	•	Burn spike detection (tokens_60s > threshold)
	•	Request storm detection (requests_60s > threshold)
	•	Evidence stored in JSON
	•	Deduplication via Redis lock key

Incident Model
	•	id
	•	type
	•	severity
	•	status (open / resolved)
	•	created_at
	•	resolved_at
	•	evidence JSON

API
	•	GET /api/v1/incidents
	•	POST /api/v1/incidents/{id}/resolve

⸻

Milestone 3 — Projects Support (Minimal Multi-Project) ✅ DONE

Backend
	•	projects table
	•	Seed demo project if empty
	•	GET /api/v1/projects

Frontend
	•	Replace free-text project input with dropdown
	•	Persist selected project in localStorage
	•	Poll only when project selected

⸻

Milestone 4 — Dashboard UI (Dark SaaS) ✅ DONE

Core UI
	•	Dark mode default
	•	Pastel accent palette
	•	Clean layout, centered container
	•	Responsive grid
	•	Sparkline SVG (no external libs)

Metrics Cards
	•	Large formatted numbers
	•	Subtext (“Last 60 seconds”)
	•	Updated timestamp
	•	Realtime sparkline

Status Strip
	•	Connected / Disconnected indicator
	•	Metrics last updated
	•	Incidents last updated

Incidents
	•	Severity badge (styled)
	•	Relative time display
	•	Details toggle
	•	Resolve button
	•	Optimistic UI update
	•	Empty state

Responsiveness
	•	2-column → 1-column metrics grid
	•	Flexible header layout
	•	Safe JSON overflow
	•	No horizontal scroll on mobile

⸻

Milestone 5 — SDK (Not Started)

Goal:
Provide lightweight SDKs for auto-reporting events.

Planned
	•	Python SDK
	•	Node.js SDK
	•	Middleware wrapper
	•	Auto-capture provider usage (OpenAI, Anthropic, Gemini)

⸻

Milestone 6 — Guardrail Mode (Not Started)

Goal:
Optional protection layer beyond monitoring.

Planned
	•	Policy model
	•	Soft blocking
	•	Model downgrade
	•	Token caps per request
	•	Retry storm detection
	•	Dry-run mode
	•	Alert webhooks (Slack / MS Teams)

⸻

Milestone 7 — Advanced Intelligence (Not Started)

Planned
	•	Adaptive thresholds
	•	Rate-of-change anomaly detection
	•	Burn projection (runway estimation)
	•	Cost attribution by feature
	•	Alert rules engine

⸻

Definition of Done (Current State)

The product currently provides:
	•	True rolling 60-second metrics
	•	Incident detection engine
	•	Multi-project support (basic)
	•	Production-grade architecture
	•	Dockerized full stack
	•	Polished responsive dark SaaS UI
