# Rollback

## Code rollback
1. Checkout previous known-good commit/tag.
2. Rebuild and start stack:
```bash
bash deploy/prod_doppler.sh up -d --build
```
3. Verify health and readiness.

## Container rollback
- If previous images are tagged in registry, pin compose to previous tags and deploy:
```bash
bash deploy/prod_doppler.sh pull
bash deploy/prod_doppler.sh up -d
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
bash deploy/prod_doppler.sh down
```
Restart all:
```bash
bash deploy/prod_doppler.sh up -d
```
Restart one service:
```bash
bash deploy/prod_doppler.sh restart backend
bash deploy/prod_doppler.sh restart worker
bash deploy/prod_doppler.sh restart scheduler
bash deploy/prod_doppler.sh restart frontend
```

## Restore last known good state
1. Deploy last known-good code/image set.
2. Verify:
```bash
curl -fsS http://localhost:${BACKEND_PORT}/health
curl -fsS http://localhost:${BACKEND_PORT}/ready
bash deploy/prod_doppler.sh ps
```
3. Confirm queue workers and scheduler are healthy.
