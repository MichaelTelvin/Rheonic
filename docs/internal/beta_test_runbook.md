# Beta Test Runbook

## Observe
Run:
- `make demo-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_DEMO_CASE=retry_storm`
- `make demo-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_DEMO_CASE=loop_suspect`
- `make demo-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_DEMO_CASE=token_explosion`

Expected:
- `incident.warn`
- no protect decision counters involved

## Protect
Run:
- `make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=clamp`
- `make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=retry_storm`
- `make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=loop_suspect`
- `make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=token_explosion`
- `make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=tok_cap_breach`
- `make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=req_cap_breach`
- `make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown`

Expected:
- `clamp` -> `protection.clamp_started`
- `tok_cap_breach` / `req_cap_breach` / `cooldown` -> `protection.block`
- behavioral scenarios still create `incident.warn` through ingest, not through preflight
