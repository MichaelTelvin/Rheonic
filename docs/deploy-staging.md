# Staging Deployment

## Prerequisites
- VPS with Docker + Docker Compose plugin.
- `staging.rheonic.dev` DNS record pointed at the VPS IP.
- Open ports `80` and `443` to the internet.
- Repo checked out on server.

## Environment file requirements
1. Create staging env:
```bash
cp .env.staging.example .env
```
2. Required values:
- `APP_ENV=staging`
- `JWT_SECRET` (>=32 chars)
- `WEBHOOK_SECRET_ENCRYPTION_KEY` (>=32 chars)
- `CORS_ORIGINS` (staging frontend origin only; no localhost)
- `DATABASE_URL`, `REDIS_URL`
- `VITE_API_BASE_URL` (public staging API URL)
- optional: `RQ_QUEUE_NAME`, `RQ_SCHEDULER_INTERVAL_SECONDS`

## HTTPS staging shape
- Staging uses `Caddy` on the VPS for TLS termination and reverse proxy.
- Public entrypoint: `https://staging.rheonic.dev`
- Caddy routes:
  - `/api/*` -> backend service on internal Docker network
  - everything else -> frontend service
- Backend and frontend are not published directly to host ports in the staging stack.

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

## Copy env to VPS
From your local machine:
```bash
scp .env root@<staging-ip>:/root/rheonic/.env
```
This assumes the repo on the VPS lives at `/root/rheonic`.
If the repo is elsewhere, change the destination path.

## Access by IP
- App: `https://staging.rheonic.dev`
- API health via Caddy: `https://staging.rheonic.dev/api/health` is not defined; use Docker exec/logs for backend verification or temporarily curl the backend container internally.
- Backend direct host access is intentionally removed from the HTTPS staging shape.

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
- Landing page loads on `https://staging.rheonic.dev`.
- TLS certificate is issued successfully by Caddy.
- Backend liveness and readiness from inside the backend container:
```bash
docker compose -f docker-compose.staging.yml exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
docker compose -f docker-compose.staging.yml exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready').read().decode())"
```
- services show healthy or running:
```bash
docker compose -f docker-compose.staging.yml ps
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
docker compose -f docker-compose.staging.yml logs -f caddy
```
- container log rotation is enabled in the staging compose file to cap local Docker log growth.

## Protect latency checks
- Protect decision latency is logged by the backend on every `/api/v1/protect/decision` call.
- SDK debug mode also logs token-estimation and preflight timing:
```bash
RHEONIC_DEBUG=1
```
