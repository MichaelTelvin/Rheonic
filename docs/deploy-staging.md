# Staging Deployment

## Prerequisites
- VPS with Docker + Docker Compose plugin.
- Open ports for staging access (typically `80` and optionally `${BACKEND_PORT}` for direct API checks).
- Repo checked out on server.

## Environment file requirements
1. Create staging env:
```bash
cp .env.example .env
```
2. Required values:
- `APP_ENV=staging`
- `JWT_SECRET` (>=32 chars)
- `WEBHOOK_SECRET_ENCRYPTION_KEY` (>=32 chars)
- `CORS_ORIGINS` (staging frontend origin only; no localhost)
- `DATABASE_URL`, `REDIS_URL`
- `VITE_API_BASE_URL` (public staging API URL)
- `FRONTEND_PORT`, `BACKEND_PORT`
- optional: `RQ_QUEUE_NAME`, `RQ_SCHEDULER_INTERVAL_SECONDS`

## Secrets handling
- There is no built-in Vault, SSM, Doppler, or cloud secret-manager integration in this repo today.
- Staging currently relies on environment-variable injection via the host `.env` file consumed by Docker Compose.
- See [`docs/secrets-management.md`](/Users/mike/Projects/Rheonic/docs/secrets-management.md) for the recommended migration path away from host-managed `.env` files.
- Treat `.env` as a host secret:
  - do not commit it,
  - keep file permissions restricted (for example `chmod 600 .env`),
  - provision it from your server secret store or CI/CD secret injection if you have one outside the repo.
- Minimum staging secrets:
  - `POSTGRES_PASSWORD`
  - `JWT_SECRET`
  - `WEBHOOK_SECRET_ENCRYPTION_KEY`

## Exact deploy commands
```bash
docker compose -f docker-compose.staging.yml up -d --build
docker compose -f docker-compose.staging.yml ps
```

## Access by IP
- Frontend: `http://<staging-ip>:${FRONTEND_PORT}`
- Backend health: `http://<staging-ip>:${BACKEND_PORT}/health`
- Backend readiness: `http://<staging-ip>:${BACKEND_PORT}/ready`

## Run migrations
- Migrations run automatically via `db_init`.
- Verify:
```bash
docker compose -f docker-compose.staging.yml logs db_init
```

## Start workers/scheduler
- Included in the staging compose stack.
- Verify running:
```bash
docker compose -f docker-compose.staging.yml ps worker scheduler
```

## Verification checklist
- Landing page loads on staging frontend port.
- API liveness and readiness:
```bash
curl -fsS "http://<staging-ip>:${BACKEND_PORT}/health"
curl -fsS "http://<staging-ip>:${BACKEND_PORT}/ready"
```
- Queue/worker visible:
```bash
docker compose -f docker-compose.staging.yml exec redis redis-cli LLEN rq:queue:${RQ_QUEUE_NAME:-rheonic}
docker compose -f docker-compose.staging.yml exec redis redis-cli KEYS "rq:worker:*"
```
- Email transport status (stub behavior expected unless real provider implemented):
  - check backend/worker logs for `email_provider_not_configured` on email jobs.
- Compliance sanity check before external access:
  - verify privacy/terms pages match actual data handling,
  - verify event retention and deletion expectations for staging data,
  - avoid using real customer data until compliance posture is finalized.

## Inspect logs
```bash
docker compose -f docker-compose.staging.yml logs -f backend
docker compose -f docker-compose.staging.yml logs -f worker
docker compose -f docker-compose.staging.yml logs -f scheduler
docker compose -f docker-compose.staging.yml logs -f frontend
```

## Protect latency checks
- Protect decision latency is logged by the backend on every `/api/v1/protect/decision` call.
- SDK debug mode also logs token-estimation and preflight timing:
```bash
RHEONIC_DEBUG=1
```
