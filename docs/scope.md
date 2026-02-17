# LLMTokenBurnGuard — Scope

## Overview

LLMTokenBurnGuard is a realtime observability and guardrail platform for LLM API usage.

It monitors:
- Token burn
- Request rates
- True rolling 60s usage windows
- Incidents (burn spikes / request storms)

It provides:
- Realtime dashboard
- Incident tracking + resolve workflow
- Projects + ingest keys management
- Clean dark SaaS UI
- True rolling window implementation (Redis ZSET)

---

## Milestone 0 — Foundation & Infrastructure ✅ DONE

### Backend
- FastAPI project skeleton
- Layered architecture (API → Service → Repository → Infrastructure)
- SQLAlchemy integration
- Postgres containerized
- Redis containerized
- RQ worker container
- Docker Compose working end-to-end
- Health endpoint

### Frontend
- Vite + React + TypeScript setup
- Dockerized frontend
- Dev proxy via Vite for backend
- CORS resolved properly

---

## Milestone 1 — Events Ingest + Realtime Metrics ✅ DONE

### Backend
- POST /api/v1/events
- Persist event to Postgres
- Redis true rolling window (ZSET-based, last 60 seconds)
- GET /api/v1/metrics/realtime
- Unit tests for rolling window logic

### Realtime Semantics
- ZSET per project for:
  - requests
  - tokens
- Score = timestamp (ms)
- Trim older than 60 seconds
- True rolling window (not TTL bucket)

---

## Milestone 2 — Incident Engine ✅ DONE

### Incident Triggering
- Burn spike detection (tokens_60s > threshold)
- Request storm detection (requests_60s > threshold)
- Evidence stored in JSON
- Deduplication via Redis lock key

### Incident Model
- id
- type
- severity
- status (open / resolved)
- created_at
- resolved_at
- evidence JSON

### API
- GET /api/v1/incidents
- POST /api/v1/incidents/{id}/resolve

---

## Milestone 3 — Projects + Ingest Keys ✅ DONE

### Backend
- projects table
- ingest_keys table (hash stored, plaintext returned once)
- GET /api/v1/projects
- POST /api/v1/projects
- GET /api/v1/projects/{project_id}/keys
- POST /api/v1/projects/{project_id}/keys
- POST /api/v1/keys/{key_id}/revoke
- POST /api/v1/keys/{key_id}/rotate
- Enforced ingest key mapping on POST /api/v1/events via header:
  - X-Project-Ingest-Key (active key required)

### Frontend
- Project dropdown (no free-text project id)
- Create Project modal
- Ingest Keys modal:
  - Create key (returns plaintext once + copy UX)
  - List keys (status, last4)
  - Rotate / revoke actions
- Persist selected project in localStorage
- Poll only when project selected

---

## Milestone 4 — Dashboard UI (Dark SaaS) ✅ DONE

### Core UI
- Dark mode default
- Pastel accent palette
- Clean layout, centered container
- Responsive grid
- Sparkline SVG (no external libs)

### Metrics Cards
- Large formatted numbers
- Subtext (“Last 60 seconds”)
- Updated timestamp
- Realtime sparkline

### Status Strip
- Connected / Disconnected indicator
- Metrics last updated
- Incidents last updated

### Incidents
- Severity badge (styled)
- Relative time display
- Details toggle
- Resolve button
- Optimistic UI update
- Empty state

### Responsiveness
- 2-column → 1-column metrics grid
- Flexible header layout
- Safe JSON overflow
- No horizontal scroll on mobile

---

## Milestone 5 — SDKs (Node + Python) ✅ DONE

### Node SDK (sdk-node)
- Async ingest (fire-and-forget) + best-effort flush-on-exit
- Bounded queue + overflow policy
- Minimal retry with small backoff (network/5xx only)
- Debug logging option (off by default)
- Demo script + README usage
- Uses header: X-Project-Ingest-Key (via LLMTBG_INGEST_KEY)

### Python SDK (sdk-python)
- Async ingest + best-effort flush-on-exit
- Bounded queue + overflow policy
- Minimal retry with small backoff (network/5xx only)
- Debug logging option (off by default)
- Demo script + README usage
- Uses header: X-Project-Ingest-Key (via LLMTBG_INGEST_KEY)

---

## Milestone 6 — Auth + Tenancy (Next) 🚧 NEXT

### Goal
Turn the system into a true multi-tenant SaaS.

### Planned (MVP Auth)
- users table (email, password hash, created_at)
- JWT-based auth:
  - POST /auth/register
  - POST /auth/login
  - auth dependency/middleware
- Tenant scoping:
  - projects belong to user_id
  - ingest_keys belong to project_id (already) → indirectly scoped to user
  - incidents/events/metrics queries scoped to authenticated user/projects
- Frontend:
  - Login page
  - Authenticated app shell
  - Store token securely (MVP: decide explicitly; start with localStorage for simplicity)

---

## Milestone 7 — Guardrail Mode (Later)

### Goal
Optional protection layer beyond monitoring.

### Planned
- Policy model
- Soft blocking
- Model downgrade
- Token caps per request
- Retry storm detection
- Dry-run mode
- Alert webhooks (Slack / MS Teams)

---

## Milestone 8 — Advanced Intelligence (Later)

### Planned
- Adaptive thresholds
- Rate-of-change anomaly detection
- Burn projection (runway estimation)
- Cost attribution by feature
- Alert rules engine

---

## Definition of Done (Current State)

The product currently provides:
- True rolling 60-second realtime metrics
- Incident detection + resolve workflow
- Projects + ingest key management
- SDKs (Node + Python) that report events to backend
- Production-grade layered architecture
- Dockerized full stack
- Polished responsive dark SaaS UI
