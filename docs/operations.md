# Operations

## Core commands

### Local
```bash
bash deploy/local_doppler.sh up -d --build
bash deploy/local_doppler.sh down
```

### Staging
```bash
bash deploy/staging_doppler.sh up -d --build
bash deploy/staging_doppler.sh down
```

### Production
```bash
bash deploy/prod_doppler.sh up -d --build
bash deploy/prod_doppler.sh down
```

## Logs
```bash
bash deploy/prod_doppler.sh logs -f backend
bash deploy/prod_doppler.sh logs -f worker
bash deploy/prod_doppler.sh logs -f scheduler
bash deploy/prod_doppler.sh logs -f frontend
bash deploy/prod_doppler.sh logs db_init
```

## Health visibility
```bash
curl -fsS http://localhost:${BACKEND_PORT}/health
curl -fsS http://localhost:${BACKEND_PORT}/ready
```

## Migrations
### Via compose bootstrap
`db_init` runs automatically before API/worker/scheduler start.

### Manual migration
```bash
cd backend
alembic -c alembic.ini upgrade head
```

## Queue and scheduler checks
```bash
bash deploy/prod_doppler.sh exec redis redis-cli LLEN rq:queue:${RQ_QUEUE_NAME:-rheonic}
bash deploy/prod_doppler.sh exec redis redis-cli KEYS "rq:worker:*"
bash deploy/prod_doppler.sh logs scheduler | tail -n 100
```

## Rebuild and restart
```bash
bash deploy/prod_doppler.sh up -d --build
bash deploy/prod_doppler.sh restart backend
bash deploy/prod_doppler.sh restart worker
bash deploy/prod_doppler.sh restart scheduler
bash deploy/prod_doppler.sh restart frontend
```

## Troubleshooting
- `ready` fails:
  - inspect backend logs
  - verify Postgres/Redis health in compose
- worker backlog growing:
  - check worker logs and Redis queue length
  - scale worker service if needed
- email notifications failing:
  - expected when provider is not configured; outbox will report `email_provider_not_configured`
- webhook failures:
  - inspect worker logs and `/api/v1/metrics/delivery-failures`
