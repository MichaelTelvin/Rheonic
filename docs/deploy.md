# Deploy

## Topology

- One VPS
- One shared Caddy instance
- One staging stack
- One production stack
- Doppler injects secrets for staging and production
- No `.env` files are required for app/runtime secrets

Domains:
- `staging.rheonic.dev` -> staging frontend/backend
- `beta.rheonic.dev` -> production frontend/backend

## Compose split

- Staging app stack: [`deploy/docker-compose.staging.yml`](../deploy/docker-compose.staging.yml)
- Production app stack: [`deploy/docker-compose.prod.yml`](../deploy/docker-compose.prod.yml)
- Shared edge proxy: [`deploy/docker-compose.proxy.yml`](../deploy/docker-compose.proxy.yml)

Isolation:
- compose projects: `rheonic_staging`, `rheonic_prod`, `rheonic_proxy`
- dedicated Docker networks:
  - `rheonic_staging_app`
  - `rheonic_staging_edge`
  - `rheonic_prod_app`
  - `rheonic_prod_edge`
- dedicated data volumes:
  - `rheonic_staging_postgres_data`
  - `rheonic_staging_redis_data`
  - `rheonic_prod_postgres_data`
  - `rheonic_prod_redis_data`

Only Caddy binds host ports `80/443`.

## Staging deploy

Normal staging deploy:

```bash
bash deploy/staging_doppler.sh up -d --build
```

Staging status:

```bash
bash deploy/staging_doppler.sh ps
```

## Production deploy

First production deployment:

1. Set production Doppler values.
2. Run migrations explicitly:

```bash
bash deploy/prod_migrate.sh
```

3. Start the production stack:

```bash
bash deploy/prod_doppler.sh up -d --build
```

Subsequent production redeploys:

```bash
bash deploy/prod_doppler.sh up -d --build
```

Normal redeploys do not require `docker compose down`.

## Production migration command

```bash
bash deploy/prod_migrate.sh
```

This starts prod Postgres/Redis if needed and then runs `db_init` as a one-off migration task.

## Caddy routing

Shared Caddy config:
- [`deploy/Caddyfile`](../deploy/Caddyfile)

Shared Caddy service:
- [`deploy/docker-compose.proxy.yml`](../deploy/docker-compose.proxy.yml)

Caddy reaches app services over the explicit edge-network aliases:
- `staging-backend`, `staging-frontend`
- `prod-backend`, `prod-frontend`

## Health checks

External/browser target:
- frontend homepage `GET /` should return `200`

Backend checks:
- liveness: `GET /health`
- readiness: `GET /ready`
- API readiness: `GET /api/v1/health`
- version: `GET /api/v1/version`

## Production-only logging

Promtail config:
- [`deploy/promtail-config.prod.yml`](../deploy/promtail-config.prod.yml)

Promtail compose path:
- [`deploy/docker-compose.promtail.yml`](../deploy/docker-compose.promtail.yml)

Start prod-only promtail:

```bash
bash deploy/prod_promtail.sh up -d
```

Stop prod-only promtail:

```bash
bash deploy/prod_promtail.sh down
```

Promtail only scrapes containers from compose project `rheonic_prod` and labels them with `env=prod`.

## Rollback

This repo builds directly from the checked-out code. Roll back by checking out the previous known-good commit/tag and redeploying:

```bash
bash deploy/prod_doppler.sh up -d --build
```
