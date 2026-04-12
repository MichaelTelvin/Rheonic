# Production Deployment

> Superseded by [`/docs/deploy.md`](./deploy.md) for the current single-VPS beta-production topology. Keep this file only for older production notes.

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
- Production secrets are expected to be injected through Doppler into the environment consumed by `docker compose`.
- See [`docs/secrets-management.md`](/Users/mike/Projects/Rheonic/docs/secrets-management.md) for the recommended integration pattern for this repo.
- Do not keep production application `.env` files in the repo or on hosts.

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
1. Ensure the production Doppler token is available on the host, for example:
```bash
printf 'DOPPLER_TOKEN=%s\n' '<service-token>' > /root/.config/rheonic/doppler.env
chmod 600 /root/.config/rheonic/doppler.env
```
2. Deploy with Doppler-backed production config:
```bash
bash deploy/prod_doppler.sh up -d --build
bash deploy/prod_doppler.sh ps
```

## Migration order
- `db_init` runs before API/worker/scheduler by compose dependency.
- Verify migration completion:
```bash
bash deploy/prod_doppler.sh logs db_init
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
bash deploy/prod_doppler.sh up -d --build db_init
bash deploy/prod_doppler.sh up -d --build backend worker scheduler frontend
```

## Smoke checklist
- `GET /health` returns `ok`.
- `GET /ready` returns `ready`.
- frontend home/dashboard loads.
- authenticated API call succeeds.
- `bash deploy/prod_doppler.sh ps` shows `backend`, `worker`, `scheduler`, and `frontend` as healthy or running.
- worker queue is active:
```bash
bash deploy/prod_doppler.sh exec redis redis-cli KEYS "rq:worker:*"
```
- scheduler running:
```bash
bash deploy/prod_doppler.sh logs scheduler | tail -n 50
```
- transport failures visible through metrics endpoint if induced.
- email alerts are either intentionally disabled or backed by a real provider.

## Recommended next production upgrades
- external log aggregation so logs survive container replacement and host-level troubleshooting is easier,
- managed or separate Postgres once load and customer reliance increase,
- stronger secret-governance around the host Doppler token,
- backups and restore drills for Postgres and Redis persistence.

## Rollback
- Follow [`docs/rollback.md`](rollback.md).
