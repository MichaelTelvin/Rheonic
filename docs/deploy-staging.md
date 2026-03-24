# Staging Deployment

> Superseded by [`/DEPLOY.md`](../DEPLOY.md) for the current beta-production topology. Keep this file only for older staging setup notes.

## Prerequisites
- VPS with Docker + Docker Compose plugin.
- Doppler CLI installed on the VPS.
- `staging.rheonic.dev` DNS record pointed at the VPS IP.
- Open ports `80` and `443` to the internet.
- Repo checked out on server.
- Doppler `rheonic/stg` config populated with the current staging values.
- A read-only `DOPPLER_TOKEN` stored on the VPS outside the repo, for example in `/root/.config/rheonic/doppler.env`.

## Required staging values
Store these in Doppler `stg`:
- `APP_ENV=staging`
- `JWT_SECRET` (>=32 chars)
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
- Staging runs directly from Doppler-injected environment variables.
- The only host-level bootstrap secret is `DOPPLER_TOKEN`.
- Do not keep a persisted application `.env` on the VPS once the Doppler flow is verified.
- See [`docs/secrets-management.md`](/Users/mike/Projects/Rheonic/docs/secrets-management.md) for the staging secret-manager model.

## Exact deploy commands
`deploy/staging_doppler.sh` auto-loads `DOPPLER_TOKEN` from `/root/.config/rheonic/doppler.env` by default.

```bash
cd /root/rheonic
bash deploy/staging_doppler.sh up -d --build
bash deploy/staging_doppler.sh ps
```

## Token bootstrap
Create a root-only token file on the VPS:
```bash
mkdir -p /root/.config/rheonic
chmod 700 /root/.config/rheonic
printf 'DOPPLER_TOKEN=%s\n' '<service-token>' > /root/.config/rheonic/doppler.env
chmod 600 /root/.config/rheonic/doppler.env
```
Then verify Doppler access:
```bash
set -a
source /root/.config/rheonic/doppler.env
set +a
doppler secrets download --project rheonic --config stg --no-file --format env | head
```

## Access by IP
- App: `https://staging.rheonic.dev`
- API health via Caddy: `https://staging.rheonic.dev/api/health` is not defined; use Docker exec/logs for backend verification or temporarily curl the backend container internally.
- Backend direct host access is intentionally removed from the HTTPS staging shape.

## Run migrations
- Migrations run automatically via `db_init`.
- Verify:
```bash
bash deploy/staging_doppler.sh logs db_init
```

## Start workers/scheduler
- Included in the staging compose stack.
- Verify running:
```bash
bash deploy/staging_doppler.sh ps worker scheduler
```

## Verification checklist
- Landing page loads on `https://staging.rheonic.dev`.
- TLS certificate is issued successfully by Caddy.
- Backend liveness and readiness from inside the backend container:
```bash
bash deploy/staging_doppler.sh exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
bash deploy/staging_doppler.sh exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready').read().decode())"
```
- services show healthy or running:
```bash
bash deploy/staging_doppler.sh ps
```
- Queue/worker visible:
```bash
bash deploy/staging_doppler.sh exec redis sh -lc 'if [ -n "$REDIS_PASSWORD" ]; then redis-cli -a "$REDIS_PASSWORD" LLEN "rq:queue:${RQ_QUEUE_NAME:-rheonic}"; else redis-cli LLEN "rq:queue:${RQ_QUEUE_NAME:-rheonic}"; fi'
bash deploy/staging_doppler.sh exec redis sh -lc 'if [ -n "$REDIS_PASSWORD" ]; then redis-cli -a "$REDIS_PASSWORD" KEYS "rq:worker:*"; else redis-cli KEYS "rq:worker:*"; fi'
```
- Email transport status (stub behavior expected unless real provider implemented):
  - check backend/worker logs for `email_provider_not_configured` on email jobs.
- Compliance sanity check before external access:
  - verify privacy/terms pages match actual data handling,
  - verify event retention and deletion expectations for staging data,
  - avoid using real customer data until compliance posture is finalized.

## Inspect logs
```bash
bash deploy/staging_doppler.sh logs -f backend
bash deploy/staging_doppler.sh logs -f worker
bash deploy/staging_doppler.sh logs -f scheduler
bash deploy/staging_doppler.sh logs -f frontend
bash deploy/staging_doppler.sh logs -f caddy
```
- container log rotation is enabled in the staging compose file to cap local Docker log growth.

## Protect latency checks
- Protect decision latency is logged by the backend on every `/api/v1/protect/decision` call.
- SDK debug mode also logs token-estimation and preflight timing:
```bash
RHEONIC_DEBUG=1
```
