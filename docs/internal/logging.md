# Logging Notes

## Protect
- `protect_action` logs final preflight outcomes:
  - `allow`
  - `clamp`
  - `block`
- block reasons:
  - `req_cap_breach`
  - `tok_cap_breach`
  - `cooldown_active`
  - `fail_closed`

## Ingest
- ingest may open behavioral incidents for:
  - `retry_storm`
  - `loop_suspect`
  - `token_explosion`

## Runtime Terminology
Current product/runtime terminology centers on:
- protect decisions: `allow`, `clamp`, `block`
- protect reasons: `token_clamp`, `req_cap_breach`, `tok_cap_breach`, `cooldown_active`, `fail_closed`
- incident types: `retry_storm`, `loop_suspect`, `token_explosion`, `block`
