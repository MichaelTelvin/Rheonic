# Manual Test Notes

## Observe Demos
Supported cases:
- `steady`
- `retry_storm`
- `loop_suspect`
- `token_explosion`

Expected results:
- incidents only for behavioral detectors
- no clamp incident
- no separate cap incident type

## Protect Demos
Supported scenarios:
- `allow`
- `clamp`
- `retry_storm`
- `loop_suspect`
- `token_explosion`
- `tok_cap_breach`
- `req_cap_breach`
- `cooldown`

Expected results:
- `allow`: request passes, no incident required
- `clamp`: decision `clamp`, webhook/email `protection.clamp_started`, no clamp incident
- `retry_storm` / `loop_suspect` / `token_explosion`: preflight stays `allow` or `clamp`; ingest opens behavioral incident
- `tok_cap_breach` / `req_cap_breach`: decision `block`, webhook/email `protection.block`, incident type `block`
- `cooldown`: repeated request blocked with `cooldown_active`
