# Production Deployment

## Prerequisites
- VPS with Docker + Docker Compose plugin.
- DNS configured for frontend and API domains.
- Reverse proxy/TLS termination configured (Nginx or Caddy on host).
- Secrets provisioned securely.
- Privacy/compliance review completed for target customers and regions.

## MVP production stance
- For an early MVP, running backend, Postgres, and Redis on one VPS is acceptable if:
  - volumes are persistent,
  - backups are enabled,
  - the host is monitored,
  - secrets are managed outside git,
  - recovery steps are documented.
- Longer term, Postgres should move to a managed or separate database service before higher-volume production use.

## Secrets handling
- The repo does not currently include a native Vault or cloud secret-manager integration.
- Production secrets are expected to be injected by your platform or deployment pipeline into the environment consumed by `docker compose`.
- See [`docs/secrets-management.md`](/Users/mike/Projects/Rheonic/docs/secrets-management.md) for the recommended integration pattern for this repo.
- Do not keep production `.env` files in the repo or on developer machines longer than necessary.

## Domain/DNS assumptions
- Frontend domain points to VPS.
- API domain points to VPS and routes to backend service port.
- `CORS_ORIGINS` contains only production frontend origin(s).

## SSL assumptions
- TLS is terminated by external reverse proxy.
- Proxy forwards to:
  - frontend container port `${FRONTEND_PORT}` (default 80 in production compose)
  - backend container port `${BACKEND_PORT}` (default 8000)

## Deployment order (exact)
1. Prepare env:
```bash
cp .env.example .env
```
2. Configure `.env` for production:
- `APP_ENV=prod` (or `production`)
- strong `JWT_SECRET`
- production `CORS_ORIGINS`
- production `DATABASE_URL` and `REDIS_URL`
- `VITE_API_BASE_URL` production API URL
3. Deploy:
```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

## Migration order
- `db_init` runs before API/worker/scheduler by compose dependency.
- Verify migration completion:
```bash
docker compose -f docker-compose.prod.yml logs db_init
```

## Service restart order
For controlled restart:
1. `db_init` (if schema changes)
2. `backend`
3. `worker`
4. `scheduler`
5. `frontend`

Example:
```bash
docker compose -f docker-compose.prod.yml up -d --build db_init
docker compose -f docker-compose.prod.yml up -d --build backend worker scheduler frontend
```

## Smoke checklist
- `GET /health` returns `ok`.
- `GET /ready` returns `ready`.
- frontend home/dashboard loads.
- authenticated API call succeeds.
- `docker compose -f docker-compose.prod.yml ps` shows `backend`, `worker`, `scheduler`, and `frontend` as healthy or running.
- worker queue is active:
```bash
docker compose -f docker-compose.prod.yml exec redis redis-cli KEYS "rq:worker:*"
```
- scheduler running:
```bash
docker compose -f docker-compose.prod.yml logs scheduler | tail -n 50
```
- transport failures visible through metrics endpoint if induced.
- email alerts are either intentionally disabled or backed by a real provider.

## Recommended next production upgrades
- external log aggregation so logs survive container replacement and host-level troubleshooting is easier,
- managed or separate Postgres once load and customer reliance increase,
- secret manager-backed deploys instead of host-managed `.env`,
- backups and restore drills for Postgres and Redis persistence.

## Rollback
- Follow [`docs/rollback.md`](rollback.md).
