# Test Runner Audit

This document is the source of truth for automated test entrypoints.

All `make test-*` targets now run through the same isolated Docker test stack:

- compose file: `docker-compose.test.yml`
- compose project: `rheonic_test`
- config source: explicit test-only container environment declared in the compose file

No automated test target depends on repo `.env` files.

## Target Matrix

### `make test-backend`

- Compose target:
  - `backend_test`
- Supporting services:
  - `postgres_test`
  - `redis_test`
  - `db_init_test`
- Config source:
  - explicit test env in `docker-compose.test.yml`
- Code path exercised:
  - FastAPI backend
  - DB/repository layer
  - application/domain services
  - migration/bootstrap path required by backend tests

### `make test-sdk-node`

- Compose target:
  - `sdk_node_unit`
- Config source:
  - container-local defaults only
- Code path exercised:
  - Node SDK unit tests
  - protect engine
  - client request shaping / failure handling

### `make test-sdk-python`

- Compose target:
  - `sdk_python_unit`
- Config source:
  - container-local defaults only
- Code path exercised:
  - Python SDK unit tests
  - protect engine
  - client retry / logging / request behavior

### `make test-frontend`

- Compose target:
  - `frontend_test`
- Config source:
  - explicit frontend test env in `docker-compose.test.yml`
  - `VITE_API_BASE_URL=https://example.invalid/api`
  - `VITE_PUBLIC_CONTACT_EMAIL=contact@rheonic.dev`
  - `VITE_APP_VERSION=test`
- Code path exercised:
  - React/Vitest unit tests
  - production frontend build
- Notes:
  - `VITE_API_BASE_URL` is intentionally non-routable. The automated frontend suite does not
    depend on a live backend and should not imply `localhost` or in-stack backend coupling.

### `make test-e2e`

- Compose targets:
  - `sdk_node_test`
  - `sdk_python_test`
- Supporting services:
  - `postgres_test`
  - `redis_test`
  - `db_init_test`
  - `backend_test`
  - `provider_stub_test`
- Config source:
  - explicit test env in `docker-compose.test.yml`
- Code path exercised:
  - backend + DB + Redis + provider stub
  - SDK end-to-end protect flow against a live test stack

## Cleanup

Normal cleanup:

```bash
make down-test
```

Explicit cleanup including volumes:

```bash
docker compose -p rheonic_test -f docker-compose.test.yml down -v
```
