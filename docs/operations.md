# Operations

## Core commands

### Local
```bash
cp .env.local.example .env
docker compose up -d --build
docker compose down
```

### Staging
```bash
bash deploy/staging_doppler.sh up -d --build
bash deploy/staging_doppler.sh down
```

### Production
```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml down
```

## Logs
```bash
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f worker
docker compose -f docker-compose.prod.yml logs -f scheduler
docker compose -f docker-compose.prod.yml logs -f frontend
docker compose -f docker-compose.prod.yml logs db_init
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
docker compose -f docker-compose.prod.yml exec redis redis-cli LLEN rq:queue:${RQ_QUEUE_NAME:-rheonic}
docker compose -f docker-compose.prod.yml exec redis redis-cli KEYS "rq:worker:*"
docker compose -f docker-compose.prod.yml logs scheduler | tail -n 100
```

## Rebuild and restart
```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml restart backend
docker compose -f docker-compose.prod.yml restart worker
docker compose -f docker-compose.prod.yml restart scheduler
docker compose -f docker-compose.prod.yml restart frontend
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
