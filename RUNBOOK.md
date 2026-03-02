# RUNBOOK

## Scope
This runbook covers first deploy, upgrades, rollback, and health verification for the runtime stack:
- `postgres`
- `redis`
- `db_init`
- `backend`
- `worker`
- `scheduler`
- `frontend`

Compose file: `docker-compose.prod.yml`

## Landing page placement decision
Use the existing frontend app as the landing page host (route-based in the same frontend deployment).  
Reason: one deployment pass, one container/service to operate, no extra static-site container.

## Prerequisites
1. Copy `.env.example` to `.env` and fill required secrets/URLs.
2. Ensure Docker and Docker Compose are installed.
3. Confirm `JWT_SECRET` is strong and not default.

## First deploy
1. Build and start:
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

2. Verify migrations completed:
```bash
docker compose -f docker-compose.prod.yml logs db_init
```
Expected: `db_init complete` and service exits successfully.

3. Verify service health:
```bash
docker compose -f docker-compose.prod.yml ps
curl -fsS http://localhost:${BACKEND_PORT}/health
curl -fsS -H "Authorization: Bearer <token>" "http://localhost:${BACKEND_PORT}/api/v1/metrics/protect?project_id=<project_id>"
```

4. Verify logs:
```bash
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f worker
docker compose -f docker-compose.prod.yml logs -f scheduler
```

## Upgrade deploy (code + migrations + restart)
1. Pull/update code.
2. Rebuild/restart:
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
3. Re-check:
```bash
docker compose -f docker-compose.prod.yml ps
curl -fsS http://localhost:${BACKEND_PORT}/health
```

## Rollback
1. Checkout previous known-good commit/tag.
2. Rebuild with previous code:
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
3. Verify health and core API responses.
4. Migration policy is forward-fix only:
   - do not run down migrations in production
   - ship a corrective migration and deploy forward

## Migration commands

### Apply migrations (prod)
```bash
cd backend
alembic -c alembic.ini upgrade head
```

### Generate migration (dev)
```bash
cd backend
alembic -c alembic.ini revision --autogenerate -m "describe_change"
```

## Worker/scheduler operational checks

### Queue depth and workers
```bash
docker compose -f docker-compose.prod.yml exec redis redis-cli LLEN rq:queue:rheonic
docker compose -f docker-compose.prod.yml exec redis redis-cli KEYS "rq:worker:*"
```

### Scheduler registration check
```bash
docker compose -f docker-compose.prod.yml logs scheduler | tail -n 50
```
Expected: scheduler bootstrap completion log and scheduler run start log.

## Incident/decision/webhook troubleshooting

### Decisions not appearing on dashboard
1. Verify preflight requests reach backend:
   - Check backend logs for `/api/v1/protect/decision`.
2. Verify protect metrics endpoint:
```bash
curl -fsS -H "Authorization: Bearer <token>" "http://localhost:${BACKEND_PORT}/api/v1/metrics/protect?project_id=<project_id>&provider=<provider>"
```

### Incidents not opening/updating
1. Verify ingest traffic:
   - Check backend logs for `/api/v1/events` 202 responses.
2. Verify incident list endpoint:
```bash
curl -fsS -H "Authorization: Bearer <token>" "http://localhost:${BACKEND_PORT}/api/v1/incidents?project_id=<project_id>&status=open&provider=<provider>"
```

### Webhooks not delivering
1. Confirm webhook is enabled and URL configured:
   - `GET /api/v1/projects/{project_id}/webhook`
2. Inspect worker logs for webhook job failures.
3. Trigger connectivity check:
   - `POST /api/v1/projects/{project_id}/webhook/test`

## Stop stack
```bash
docker compose -f docker-compose.prod.yml down
```
