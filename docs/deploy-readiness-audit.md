# Deploy Readiness Audit

## 1. Executive Summary
- Scope audited: backend, frontend, workers/scheduler, transport hub, migrations, compose/Docker, tests, docs.
- Result: staging-ready for internal validation after fixes in this pass; not fully production-ready until TLS, secret rotation, email delivery, and compliance decisions are completed.

## 2. What Was Found
- Production safety gaps:
  - no `/ready` dependency check endpoint
  - permissive CORS fallback to localhost when `CORS_ORIGINS` empty
  - no strict staging/prod config validation for JWT/CORS/webhook encryption key
  - production compose exposed Postgres/Redis ports publicly
  - production frontend built on container startup instead of image build
  - queue name hardcoded in multiple services
  - tracked `.env` contained sensitive values
- Repo hygiene gaps:
  - duplicate/stale deployment docs (`RUNBOOK.md`, `PRODUCTION_DEPLOY_READINESS.md`)
  - no root deploy docs set for staging/prod/rollback/operations
  - no `.dockerignore` files for backend/frontend
- Test coverage gaps:
  - no explicit config validation tests
  - no readiness endpoint tests

## 3. What Was Fixed
- Config model hardening:
  - [`backend/app/config.py`](/Users/mike/Projects/Rheonic/backend/app/config.py)
  - Added production-like validation:
    - `APP_ENV` allowed set enforced
    - `JWT_SECRET` minimum length for staging/prod
    - `CORS_ORIGINS` required and localhost rejected for staging/prod
  - Added unified runtime settings:
    - `RQ_QUEUE_NAME`
    - `RQ_SCHEDULER_INTERVAL_SECONDS`
    - `TRUST_PROXY_HEADERS`
    - `FORWARDED_ALLOW_IPS`
- Health/readiness + CORS tightening:
  - [`backend/app/main.py`](/Users/mike/Projects/Rheonic/backend/app/main.py)
  - Added `/ready` with DB + Redis checks
  - Kept `/health` as liveness
  - tightened CORS methods/headers
- Redis health utility:
  - [`backend/app/infrastructure/redis/redis_client.py`](/Users/mike/Projects/Rheonic/backend/app/infrastructure/redis/redis_client.py)
  - Added `ping()`
- Queue consistency:
  - [`backend/app/infrastructure/jobs/transport_job.py`](/Users/mike/Projects/Rheonic/backend/app/infrastructure/jobs/transport_job.py)
  - [`backend/app/workers/scheduler.py`](/Users/mike/Projects/Rheonic/backend/app/workers/scheduler.py)
  - [`backend/app/workers/scheduler_bootstrap.py`](/Users/mike/Projects/Rheonic/backend/app/workers/scheduler_bootstrap.py)
  - queue now driven by settings/env, not hardcoded
- Container/runtime hardening:
  - [`backend/Dockerfile`](/Users/mike/Projects/Rheonic/backend/Dockerfile): `INSTALL_DEV` build arg
  - added [`frontend/Dockerfile.prod`](/Users/mike/Projects/Rheonic/frontend/Dockerfile.prod) for production static build
  - added docker ignore files:
    - [`backend/.dockerignore`](/Users/mike/Projects/Rheonic/backend/.dockerignore)
    - [`frontend/.dockerignore`](/Users/mike/Projects/Rheonic/frontend/.dockerignore)
  - updated compose files:
    - [`docker-compose.yml`](/Users/mike/Projects/Rheonic/deploy/docker-compose.yml) (queue env consistency)
    - [`docker-compose.test.yml`](/Users/mike/Projects/Rheonic/deploy/docker-compose.test.yml) (backend build args + readiness healthcheck)
    - [`docker-compose.prod.yml`](/Users/mike/Projects/Rheonic/deploy/docker-compose.prod.yml) (no DB/Redis host port exposure, proxy headers, readiness healthcheck, production frontend Dockerfile)
    - added [`docker-compose.staging.yml`](/Users/mike/Projects/Rheonic/deploy/docker-compose.staging.yml)
- Secrets/config hygiene:
  - sanitized tracked [`/.env`](/Users/mike/Projects/Rheonic/.env) to remove sensitive values
  - updated [`/.env.example`](/Users/mike/Projects/Rheonic/.env.example) for staging/prod-safe defaults
  - added [`/.env.local.example`](/Users/mike/Projects/Rheonic/.env.local.example)
  - updated [`.gitignore`](/Users/mike/Projects/Rheonic/.gitignore) to allow `.env.local.example`
  - confirmed current staging/prod secret handling is environment-based only; no native Vault/secret-manager integration exists in-repo today
- Tests added:
  - [`backend/app/tests/test_settings_validation.py`](/Users/mike/Projects/Rheonic/backend/app/tests/test_settings_validation.py)
  - [`backend/app/tests/test_health_readiness.py`](/Users/mike/Projects/Rheonic/backend/app/tests/test_health_readiness.py)
- Deployment docs consolidation:
  - removed stale: [`RUNBOOK.md`](/Users/mike/Projects/Rheonic/RUNBOOK.md), [`PRODUCTION_DEPLOY_READINESS.md`](/Users/mike/Projects/Rheonic/PRODUCTION_DEPLOY_READINESS.md)
  - updated [`README.md`](/Users/mike/Projects/Rheonic/README.md)

## 4. What Remains As Manual/Product Decisions
- Reverse proxy + TLS termination strategy (Nginx/Caddy on VPS host) and certificate automation.
- Final production domain and DNS cutover.
- Email provider implementation behind current stub transport (currently deterministic fail-state by design when provider disabled/unimplemented).
- External log aggregation remains a recommended production upgrade; current compose files now cap Docker log size locally, but logs are not yet shipped off-host.
- Secrets manager integration (Doppler)
- Privacy/compliance review:
  - confirm data retention policy for events and incidents,
  - confirm customer-facing privacy language and subprocessors,
  - decide whether GDPR-facing materials (privacy policy, DPA, deletion/export workflow) are required for target customers before production launch.

## 5. Staging Readiness Status
- Status: **READY FOR INTERNAL STAGING**
- Required before deploy:
  - create `.env` from `.env.example`
  - set real staging secrets and domains
  - run staging smoke checks in `docs/deploy-staging.md`

## 6. Production Readiness Status
- Status: **READY WITH CONDITIONS**
- Conditions:
  - reverse proxy + TLS in place
  - production secrets provisioned/rotated
  - compliance/privacy review completed
  - real email provider implemented if email alerts are expected to work
  - deployment and smoke checklist in `docs/deploy-production.md` completed

## 7. Risk Register
- R1: No built-in TLS in compose stack.
  - Mitigation: external reverse proxy with TLS.
- R2: Email provider intentionally stubbed.
  - Mitigation: transport outbox captures failures (`email_provider_not_configured`); add real provider before relying on email delivery.
- R3: Forward-fix migration policy.
  - Mitigation: no down migration in prod; rollback is image/code rollback plus corrective forward migration.
- R4: Single-host Postgres/Redis for MVP production.
  - Mitigation: acceptable early with persistent volumes and backups; move to managed or separate data services as load and criticality increase.
