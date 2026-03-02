# Production Deploy Readiness Report

## Service/Entrypoint Inventory

### Runtime services
- Backend API: `uvicorn app.main:app` (`docker-compose.yml`, `backend/app/main.py`)
- Background worker: `rq worker --url "$REDIS_URL" rheonic` (`docker-compose.yml`)
- Scheduler: `python -m app.workers.scheduler_bootstrap && python -m app.workers.scheduler` (`docker-compose.yml`, `backend/app/workers/scheduler*.py`)
- Postgres: `postgres:16-alpine`
- Redis: `redis:7-alpine`
- Frontend app: Vite (`npm run dev` in dev compose)

### Dev/test-only services
- Provider stub: `python /app/tests/e2e/provider_stub.py` (`docker-compose.yml`, `docker-compose.test.yml`, `tests/e2e/provider_stub.py`)
- SDK test runners: `sdk_node`, `sdk_python`, `frontend_test` (compose test/dev tooling only)

## Compose and Commands Scan

### `docker-compose.yml`
- Includes runtime + dev/test helpers in one file (`backend`, `worker`, `scheduler`, `frontend`, `sdk_*`, `frontend_test`, `provider_stub`)
- Backend runs with `--reload` and bind-mounts source (`./backend:/app`)
- Frontend runs dev server and installs deps on start

### `docker-compose.test.yml`
- Isolated test stack (`postgres_test`, `redis_test`, `backend_test`, `provider_stub_test`, sdk e2e runners)
- Used by `make test-backend` and `make test-e2e`

### Make targets
- `test-backend`, `test-frontend`, `test-sdk-node`, `test-sdk-python`, `test-e2e`
- No production target existed before this pass

## Environment Variables (consumed) and prod requirement

### Required in production
- `DATABASE_URL` (`backend/app/infrastructure/db/base.py`)
- `REDIS_URL` (`backend/app/infrastructure/redis/redis_client.py`)
- `JWT_SECRET` (`backend/app/dependencies.py` -> auth token validation)
- `CORS_ORIGINS` (`backend/app/main.py`)
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` (postgres container)
- `VITE_API_BASE_URL` (frontend runtime build target)

### Strongly recommended in production
- `APP_ENV`
- `AUTO_CLOSE_RUN_INTERVAL_SECONDS`
- `LOG_LEVEL`

### Dev/test/demo only
- `RHEONIC_*` demo/e2e variables (sdk demos/e2e scripts)

## DB Migration/Schema status

- Alembic is the operational schema path:
  - config: `backend/alembic.ini`
  - env: `backend/alembic/env.py`
  - baseline migration: `backend/alembic/versions/20260226_01_initial_schema.py`
- Production bootstrap now applies migrations with:
  - `python -m app.infrastructure.db.migrate` (from `db_init` in `docker-compose.prod.yml`)
  - the migration module runs `alembic upgrade head` and stamps existing legacy schema once when needed

## CORS/Auth in production

- CORS middleware configured from `CORS_ORIGINS` (comma-separated), fallback `http://localhost:5173` only when empty (`backend/app/main.py`)
- Auth:
  - Bearer JWT validated in dependency (`backend/app/dependencies.py`, `backend/app/security/jwt_tokens.py`)
  - Ingest routes protected by `X-Project-Ingest-Key`

## Health and metrics endpoints

- Health:
  - `GET /health` returns `{"status":"ok"}` (`backend/app/main.py`)
- Metrics:
  - `GET /api/v1/metrics/realtime`
  - `GET /api/v1/metrics/protect`
  - `GET /api/v1/metrics/protect/health`

---

## ✅ Ready

- Backend API health endpoint exists and returns 200 (`backend/app/main.py`).
- Worker and scheduler entrypoints are implemented and runnable (`backend/app/workers/scheduler.py`, `backend/app/workers/scheduler_bootstrap.py`, `docker-compose.yml` commands).
- Core infra services (Postgres/Redis) already include healthchecks in compose files.
- Auth and CORS are already configurable via env.
- Test stack and e2e stack are isolated and reproducible via `make`.

## ⚠️ Risky / unclear

1. Dev compose mixed runtime and dev/test-only services.
   - Reference: `docker-compose.yml`
   - Risk: unclear operator path for first production deploy.

2. Frontend container in dev compose runs Vite dev server (`npm run dev`), not production serving.
   - Reference: `docker-compose.yml`, `frontend/Dockerfile`

## ❌ Missing / blockers (and exact fixes)

1. Missing production compose profile (runtime-only, no provider stub/sdk test services).
   - Fix implemented: `docker-compose.prod.yml`

2. Missing explicit schema migration step for deploy.
   - Fix implemented: `db_init` service in `docker-compose.prod.yml` now runs `python -m app.infrastructure.db.migrate` and gates API/worker/scheduler startup.

3. Missing committed production env template.
   - Fix implemented: `.env.example`
   - Also fixed ignore rule to allow it: `.gitignore` now includes `!.env.example`.

4. Missing operator documentation for deploy/upgrade/rollback/health checks.
   - Fix implemented: `RUNBOOK.md`

5. Missing SDK release procedure documentation.
   - Fix implemented: `RELEASE.md`

## Remaining known risk (factual)

- Rollback is forward-fix only in current operational docs; no automatic down-migration runbook is defined for production deploys.
