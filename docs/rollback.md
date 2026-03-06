# Rollback

## Code rollback
1. Checkout previous known-good commit/tag.
2. Rebuild and start stack:
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
3. Verify health and readiness.

## Container rollback
- If previous images are tagged in registry, pin compose to previous tags and deploy:
```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

## Migration rollback policy
- Production policy: **forward-fix only**.
- Do not run destructive down migrations in production.
- If deploy introduces schema issue:
  - roll back app containers to previous version
  - create corrective forward migration
  - redeploy

## Emergency stop/restart
Stop all:
```bash
docker compose -f docker-compose.prod.yml down
```
Restart all:
```bash
docker compose -f docker-compose.prod.yml up -d
```
Restart one service:
```bash
docker compose -f docker-compose.prod.yml restart backend
docker compose -f docker-compose.prod.yml restart worker
docker compose -f docker-compose.prod.yml restart scheduler
docker compose -f docker-compose.prod.yml restart frontend
```

## Restore last known good state
1. Deploy last known-good code/image set.
2. Verify:
```bash
curl -fsS http://localhost:${BACKEND_PORT}/health
curl -fsS http://localhost:${BACKEND_PORT}/ready
docker compose -f docker-compose.prod.yml ps
```
3. Confirm queue workers and scheduler are healthy.
