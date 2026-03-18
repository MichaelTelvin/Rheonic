# Rheonic

Rheonic is a runtime safety layer for LLM applications with:
- FastAPI backend
- PostgreSQL + Redis
- RQ worker + scheduler
- React/Vite frontend
- unified outbox-based transport hub for webhook + email delivery

## Local development
1. Start local stack through Doppler:
```bash
bash deploy/local_doppler.sh up -d --build
```
2. Verify:
```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready
```

## Deployment docs
- Audit: [`docs/deploy-readiness-audit.md`](docs/deploy-readiness-audit.md)
- Staging: [`docs/deploy-staging.md`](docs/deploy-staging.md)
- Production: [`docs/deploy-production.md`](docs/deploy-production.md)
- Rollback: [`docs/rollback.md`](docs/rollback.md)
- Operations: [`docs/operations.md`](docs/operations.md)

## Transport notifications
- Notification catalog: [`NOTIFICATION_CATALOG.md`](NOTIFICATION_CATALOG.md)

## License
MIT
