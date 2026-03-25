# Beta Test Runbook

Use this runbook for the final pre-beta end-to-end validation pass.

Scope:
- backend
- frontend
- worker / scheduler
- webhook + email transport
- Python SDK
- Node SDK
- public docs / contracts

Run the steps in order. Do not skip the automated gate.

## 0. Preconditions

- current commit is pushed
- staging is reset and redeployed from that commit
- webhook destination is available
- email delivery is configured in staging
- one clean project will be used for the full pass

## 1. Automated Gate

Run locally:

```bash
make test-backend
make test-sdk-python
make test-sdk-node
make test-frontend
make test-e2e
make check

make down-test  -> to tear down test containers
```

Expected:
- all suites pass

If anything fails, stop here and fix before manual testing.

## 2. Staging Reset

Run on the VPS in `/root/rheonic`:

```bash
git pull
bash deploy/staging_doppler.sh down -v
bash deploy/staging_doppler.sh up -d --build
bash deploy/staging_doppler.sh logs db_init
bash deploy/staging_doppler.sh exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready').read().decode())"
bash deploy/staging_doppler.sh exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select version_num from alembic_version;"'
bash deploy/staging_doppler.sh ps
```

Expected:
- `db_init` succeeds
- `/ready` returns success
- alembic version is `20260317_01`
- core containers are healthy

## 3. UI Smoke

Open staging fresh in the browser.

Check:
- Landing page
- Login / register
- Dashboard
- Projects
- Keys
- Incidents
- Protect
- Alerts
- Docs viewer

Expected:
- no browser console app errors
- no major layout jitter
- no delayed empty-state pop-ins on Keys / Incidents
- DPA / Terms / Privacy links work

## 4. Auth And Tenancy

Use two accounts or two browser sessions.

Validate:
1. register
2. login
3. refresh/session continuity
4. logout
5. cross-tenant access is blocked for:
   - projects
   - keys
   - incidents
   - metrics

Light auth abuse sanity check:
- repeated bad logins eventually 429
- repeated refresh hammering eventually 429

## 5. Project And Key Lifecycle

Using one clean project:

1. Create project
2. Create ingest key
3. Rotate key
4. Revoke old key
5. Confirm only the active key works
6. Confirm providers list is empty before traffic
7. Delete a disposable extra project and confirm cleanup

## 6. Alerts Setup

In `Alerts`:

1. Enable email
2. Enable webhook
3. Set a real webhook URL
4. Click `View payload`
5. Copy sample JSON
6. Click `Test webhook`
7. Click `Save alerts`

Expected:
- success/failure toast appears for the test
- `Last live webhook delivery` does not change because test sends are excluded
- sample payload matches public docs

## 7. Observe Mode

Set project mode to `Observe`.

Run:

```bash
make demo-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_DEMO_CASE=steady
make demo-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_DEMO_CASE=near_cap
make demo-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_DEMO_CASE=retry_storm
make demo-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_DEMO_CASE=loop_suspect
make demo-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_DEMO_CASE=token_explosion
make demo-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_DEMO_CASE=cap_breach
make demo-stg-python RHEONIC_PROVIDER=google RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=steady
```

Expected:
- `steady`: traffic ingests, no anomaly alert
- `near_cap`: `incident.warn`
- `retry_storm`: `incident.warn`
- `loop_suspect`: `incident.warn`
- `token_explosion`: `incident.warn`
- `cap_breach`: `incident.warn`
- first-seen `(provider, model)`: `policy_gap.detected`
- no `protection.*` events in Observe

Verify:
- dashboard counters move
- incidents appear in UI
- webhook delivery succeeds

## 8. Observe Resolved

Resolve one Observe incident manually.

Expected:
- `incident.resolved` webhook is sent
- no email is sent in Observe

## 9. Protect Mode

Switch project mode to `Protect`.

If the project is still in `Observe`, protect demos can still return `allow` and the
provider call can still happen, but the Protect decision counters will stay at zero by design.

Run:

```bash
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=allow
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=near_cap
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=retry_storm
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=loop_suspect
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=token_explosion
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cap_breach
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=req_cap_breach
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown
```

Expected:
- `allow`: no alert
- `near_cap`: `protection.warn`
- `retry_storm`: `protection.warn`
- `loop_suspect`: `protection.warn`
- `token_explosion`: `protection.warn`
- `cap_breach`: `protection.block` with `reason=cap_breach`
- `req_cap_breach`: `protection.block` with `reason=cap_breach`, `detail_reason=req_cap_breach`
- `cooldown`: one `protection.block(reason=cap_breach)`, then one `protection.block(reason=cooldown_active)`

Verify:
- provider call behavior matches the decision
- webhook and email carry the same core Protect semantics
- no duplicate protect events for one episode

## 10. Clamp OFF / ON

### Clamp OFF
Disable clamp in Protect settings, then run:

```bash
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=near_cap
```

Expected:
- warn only
- original max token budget preserved
- no applied clamp

### Clamp ON
Enable clamp in Protect settings, then run:

```bash
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=near_cap
```

Expected:
- warn
- effective provider request uses clamped max output tokens
- one `protection.clamp_started`

Repro values that should force a real clamp with the current staging defaults:

```bash
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=near_cap RHEONIC_NEAR_CAP_SEED_TOKENS=1870
```

Expected:
- protect returns `warn`
- `recommended_max_output_tokens` is lower than `128`
- provider call uses the reduced token cap
- `protection.clamp_started` email is sent

## 11. Fail Mode

Switch Protect fail mode and verify both paths.

### Fail Open
Set fail mode to `open`, then make protect decision unavailable temporarily and run:

```bash
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=allow RHEONIC_PROTECT_DECISION_TIMEOUT_MS=30
```

Expected:
- request is allowed through
- no provider-side block happens
- backend records decision timeout or unavailable telemetry

### Fail Closed
Set fail mode to `closed`, then make protect decision unavailable temporarily and run:

```bash
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=allow RHEONIC_PROTECT_DECISION_TIMEOUT_MS=30
```

Expected:
- request is blocked
- no provider call is made
- reason resolves to `decision_unavailable` or fail-closed equivalent
## 12. Protect Resolved

Resolve one Protect incident manually.

Expected:
- `incident.resolved` webhook is sent
- `incident.resolved` email is sent

If practical, also wait for one stale incident auto-close and verify the same semantics.

## 13. Webhook Failure Path

Set a broken webhook URL in `Alerts`, keep email enabled, then trigger a real Protect event:

```bash
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=retry_storm
```

Expected:
- worker retries delivery
- terminal failure is recorded
- dashboard banner shows recent webhook delivery issues
- `webhook.delivery_failed` email is sent

Then:
1. Click `Test webhook` with the broken URL
2. Verify this alone does not create the dashboard banner or the failure email

Restore a valid webhook URL after that.

## 14. SDK Validation

### Python
Run:

```bash
make demo-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_DEMO_CASE=steady
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=retry_storm
```

Verify:
- structured JSON SDK logs
- `X-Trace-ID` propagation
- no Python-specific behavior divergence

### Node
Run:

```bash
make demo-stg-node RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_DEMO_CASE=steady
make protect-stg-node RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=retry_storm
```

Verify:
- structured JSON SDK logs
- same semantics as Python

## 15. Logging Spot Check

On staging:

```bash
bash deploy/staging_doppler.sh logs backend --tail=200
bash deploy/staging_doppler.sh logs worker --tail=200
bash deploy/staging_doppler.sh logs scheduler --tail=100
```

Verify:
- logs are JSON
- `trace_id` and `service` are present
- no secrets/tokens are logged
- no full request/webhook payload dumps
- worker logs show expected outbox lifecycle events

## 16. Docs / Contract Sanity

Open and verify:
- `Quickstart`
- `Alerts`
- `Protect Mode`
- `Incidents`
- `API Reference`
- architecture charts

Confirm:
- alert contract names are correct
- sample webhook payload is current
- SDK logging guidance is present
- no old webhook editor wording remains
- no old `decision.warn` / `incident.block` transport wording remains


## 17. Perform the same checks with multiple projects

## 18. Final Sign-Off

Beta is ready only if all are true:

- automated gate passed
- staging reset/deploy clean
- Observe scenarios passed
- Protect scenarios passed
- webhook failure path passed
- email delivery path passed
- SDK Python and Node paths passed
- logs are structured and traceable
- docs match runtime behavior
- no unexplained duplicate notifications
- no serious browser console or worker errors

## Shortest Serious Pass

If you need the minimum acceptable full-system pass, run:

```bash
make test-backend
make test-sdk-python
make test-sdk-node
make test-frontend
make test-e2e
make demo-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_DEMO_CASE=near_cap
make demo-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_DEMO_CASE=cap_breach
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=near_cap
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=retry_storm
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cap_breach
make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown
```

Then manually verify:
- one resolved incident in Observe
- one resolved incident in Protect
- one real webhook failure path
- one webhook test path
- docs pages
