# Secrets Management

## Recommended model
- Local development:
  - use `.env.local` or `.env` that is never committed,
  - keep placeholders in `.env.example`,
  - rotate local secrets when shared accidentally.
- Staging and production:
  - do not treat `.env` as the source of truth,
  - use a secret manager as the source of truth,
  - inject secrets into environment variables only at deploy or process start.

This repo is already environment-driven, so integration should happen outside application code. The app should continue reading:
- `DATABASE_URL`
- `REDIS_URL`
- `POSTGRES_PASSWORD`
- `JWT_SECRET`
- `CORS_ORIGINS`
- any future email/provider credentials

## Why use a secret manager instead of `.env`
- `.env` is static and easy to leak through shells, backups, screenshots, or accidental commits.
- Secret managers give access control, audit logs, rotation workflows, and scoped machine identities.
- The application code stays simple because secrets still arrive as ordinary environment variables.

## Integration pattern for this repo
1. Store staging or production secrets in the secret manager.
2. Authenticate the deploy host, CI runner, or entrypoint process to that manager.
3. Start Compose through the secret manager so the required values are present in the process environment.
4. Keep `.env.example` only as a shape/template for local workflows, not as a deployed secret file.

## Practical options

### Doppler
- Good fit when you want a simple hosted secrets workflow for Docker Compose and CI.
- Typical pattern:
  - store all env vars in a Doppler project/config,
  - provide `DOPPLER_TOKEN` from CI or the server,
  - run Compose through `doppler run --project rheonic --config stg -- docker compose -f docker-compose.staging.yml up -d --build`.
- In this repo, staging Compose no longer needs a persisted app `.env` file when run this way.

### 1Password
- Good fit when the team already lives in 1Password.
- Typical pattern:
  - create a service account with least-privilege access,
  - provide `OP_SERVICE_ACCOUNT_TOKEN` to CI or the server,
  - resolve secrets at runtime with `op run -- docker compose ...`.

### HashiCorp Vault
- Good fit when you want stronger infrastructure control, dynamic secrets, or self-hosted governance.
- Typical pattern:
  - authenticate the host or workload to Vault,
  - use Vault Agent to render secrets to environment variables or files,
  - start Compose or the backend process with those values available.

## Recommended rollout for Rheonic
- Step 1: keep local development on `.env.local`.
- Step 2: move staging to Doppler or 1Password first because the repo is already Compose-based.
- Step 3: keep production on the same tool if operationally sufficient, or move to Vault if you need dynamic DB credentials, stricter separation, or broader infrastructure policy.

## What not to do
- Do not commit real `.env` files.
- Do not bake secrets into Docker images.
- Do not hardcode secrets in compose YAML.
- Do not pass secret-manager tokens to app code unless the app truly needs direct read access.

## Minimum server workflow
```bash
bash deploy/staging_doppler.sh up -d --build
```

The only host-level bootstrap secret in that flow is the secret-manager token itself.
