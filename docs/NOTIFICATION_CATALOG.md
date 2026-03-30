# Notification Catalog

This document reflects the current alerting contract after the observe/protect separation refactor.

## Principles
- Observe reports behavioral incidents.
- Protect enforces runtime limits and clamp decisions.
- Clamp uses internal projected-budget math, but there is no separate customer-facing warning concept for it.

## Runtime Events

| Event type | Kind | Source | Meaning |
|---|---|---|---|
| `incident.warn` | webhook + email | `IncidentManager` | A new behavioral incident episode opened: `retry_storm`, `loop_suspect`, or `token_explosion` |
| `incident.resolved` | webhook + email | incident resolve flows | An open incident was resolved or auto-resolved |
| `protection.clamp_started` | webhook + email | `ProtectService` | Protect started actively clamping output tokens |
| `protection.block` | webhook + email | `ProtectService` | Protect blocked the request because of `req_cap_breach`, `tok_cap_breach`, `cooldown_active`, or `fail_closed` |
| `policy_gap.detected` | webhook | ingest policy-gap flow | A new `(project, provider, model)` tuple appeared after a baseline already existed |
| `webhook.delivery_failed` | email | transport worker | A real webhook delivery reached terminal failure |
| `webhook.test` | webhook | webhook test endpoint | Explicit user-triggered connectivity test |
| `feedback.submitted` | email | feedback endpoint | Internal product feedback notification |

## Protect Reporting Rules
- Protect preflight returns only `allow`, `clamp`, or `block`.
- Clamp is a protect behavior, not an incident.
- A protect-side incident opens only for a real block, as `incident_type=block`.

## Incident Rules
- Behavioral incidents:
  - `retry_storm`
  - `loop_suspect`
  - `token_explosion`
- Protect block incident:
  - `block`

## Mode Matrix

| Event | Observe | Protect |
|---|---|---|
| `incident.warn` | Yes | Yes |
| `incident.resolved` | Yes | Yes |
| `protection.clamp_started` | No | Yes |
| `protection.block` | No | Yes |
| `policy_gap.detected` | Yes | Yes |
| `webhook.delivery_failed` | No | Yes |

## Email Templates
- `incident_warn`
- `incident_resolved`
- `protection_clamp_started`
- `protection_block`
- `webhook_delivery_failed`
- `feedback_submitted`
