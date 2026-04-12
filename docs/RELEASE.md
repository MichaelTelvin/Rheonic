# Release

## Source of truth

- Root version source: [`VERSION`](../VERSION)
- Update code/package metadata from `VERSION`:

```bash
python3 scripts/sync_version.py
```

`VERSION` uses semver for app and npm releases. Python prereleases are derived automatically:
- `0.2.0` -> `0.2.0`
- `0.2.0-beta.1` -> `0.2.0b1`

## Beta release flow

1. Update [`VERSION`](../VERSION)
2. Sync package metadata:

```bash
python3 scripts/sync_version.py
```

3. Run validation:

```bash
make check
make test
make test-e2e
```

4. Deploy staging:

```bash
bash deploy/staging_doppler.sh up -d --build
```

5. Verify staging, then deploy beta production:

```bash
bash deploy/prod_doppler.sh up -d --build
```

## Runtime version behavior

- Backend runtime version comes from `APP_VERSION` or the installed `rheonic-backend` package version.
- Frontend UI version comes from `VITE_APP_VERSION`.
- Both deploy scripts export `APP_VERSION` and `VITE_APP_VERSION` from [`VERSION`](../VERSION) automatically.

## Safe migration step

Run production migrations separately when you want an explicit migration checkpoint:

```bash
bash deploy/prod_migrate.sh
```

## Rollback

This VPS deploy builds from the checked-out repo. The normal rollback path is:

1. Checkout the previous known-good commit or tag.
2. Redeploy:

```bash
bash deploy/prod_doppler.sh up -d --build
```

If you later move to prebuilt images, pin the previous image tag in compose and redeploy with the same command.
