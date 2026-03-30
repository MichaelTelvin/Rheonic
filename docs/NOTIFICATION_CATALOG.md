# Notification Catalog

This catalog reflects the implemented notification contract.

## Transport Path (single path)
- Emitters call `WebhookDispatcher.enqueue(...)` or `TransportService.enqueue(...)`.
- `RQWebhookDispatcher` writes to `transport_outbox` via `TransportService`.
- Worker job `process_outbox_delivery` sends webhook/email asynchronously and updates outbox state.
- Dashboard delivery-failure card reads aggregated outbox statuses (`failed`/`dead`) via `GET /api/v1/metrics/delivery-failures`.
- Delivery-health views intentionally exclude `webhook.test`; only real alert dispatches count as webhook delivery issues.

## Runtime Event Catalog

| Event type | Kind | Emitter(s) | Payload schema (current keys) | Intended recipient(s) | Mode gating |
|---|---|---|---|---|---|
| `incident.warn` | webhook | `IncidentManager._enqueue_detection_notifications` | `event`, `project_id`, `incident_id`, `incident_type`, `provider`, `model`, `environment`, `created_at`, `last_seen_at`, `sent_at`, `evidence` | Project webhook URL (`projects.webhook_url`) | Observe only |
| `protection.warn` | webhook + email | `ProtectService` warn reporting path | `event`, `project_id`, `provider`, `model`, `environment`, `reason`, `requests_60s`, `tokens_60s`, `req_cap`, `tok_cap`, `estimated_next_tokens`, `apply_clamp_enabled`, `clamp`, `sent_at` | Project webhook URL + owning user account email | Protect only |
| `protection.clamp_started` | webhook + email | `ProtectService` clamp reporting path | `event`, `project_id`, `provider`, `model`, `environment`, `reason`, `requests_60s`, `tokens_60s`, `req_cap`, `tok_cap`, `estimated_next_tokens`, `clamp`, `sent_at` | Project webhook URL + owning user account email | Protect only; once when clamp first begins affecting traffic |
| `protection.block` | webhook + email | `ProtectService` block reporting path + fail-closed fallback reporting path | `event`, `project_id`, `provider`, `model`, `environment`, `reason`, `detail_reason`, `requests_60s`, `tokens_60s`, `req_cap`, `tok_cap`, `blocked_until`, `retry_after_seconds`, `source`, `sent_at` | Project webhook URL + owning user account email | Protect only |
| `incident.resolved` | webhook + email | `DetectIncidentsService` and `AutoCloseIncidentsService` resolved enqueue paths | `event`, `project_id`, `incident_id`, `incident_type`, `resolved_by`, `resolved_at`, `created_at`, `last_seen_at`, `provider`, `model`, `environment`, `sent_at` | Project webhook URL + owning user account email | Observe + Protect |
| `policy_gap.detected` | webhook | `IngestEventService._detect_policy_gap_if_needed` | `event`, `project_id`, `provider`, `model`, `first_seen_at`, `sent_at` | Project webhook URL | Observe + Protect; new `(project, provider, model)` only after the project already has baseline provider/model history |
| `webhook.delivery_failed` | email | transport worker terminal webhook failure hook | `project_id`, `event_type`, `destination`, `status`, `attempts`, `max_attempts`, `last_error_code`, `last_error_message`, `updated_at` | Owning user account email | Protect only; only when webhook is enabled and terminal failure is reached |
| `webhook.test` | webhook | `POST /api/v1/projects/{project_id}/webhook/test` | `event`, `project_id`, `sent_at` | Project webhook URL or test override URL | Mode-independent; excluded from delivery-failure banner/email |
| `feedback.submitted` | email | `POST /api/v1/feedback` | `message`, `email`, `user_id`, `user_email`, `project_id`, `page`, `mode`, `timestamp`, `app_version` | Feedback report address (`Settings.feedback_report_email`) | Mode-independent (authenticated feedback action) |

## Delivery Policy Matrix

### Policy principles
- Observe transports describe what Rheonic saw.
- Protect transports describe what Protect did.
- Email and webhook share the same core Protect semantics; webhook may be richer in structure, but not richer in meaning.
- `incident.resolved` remains the shared lifecycle closure signal in both modes.
- Protect reporting must avoid per-request spam; warn/clamp/block alerts emit on meaningful transition points, not on every repeated decision.
- Policy-gap remains webhook-only in MVP.

### Core alert tiers
- Observe lifecycle alerts:
  - `incident.warn`
  - `incident.resolved`
- Protect reporting alerts:
  - `protection.warn`
  - `protection.clamp_started`
  - `protection.block`
  - `incident.resolved`
  - `webhook.delivery_failed`
- Auxiliary signals:
  - `policy_gap.detected`
  - `feedback.submitted`
  - `webhook.test`

### Matrix

| Event / Condition | Observe dashboard state | Observe webhook | Observe email | Protect dashboard state | Protect webhook | Protect email | Notes |
|---|---|---|---|---|---|---|---|
| `feedback.submitted` | No | No | Internal only | No | No | Internal only | Product/admin workflow, not customer-facing alerting |
| `policy_gap.detected` | Not represented in incident counters | Yes | No | Not represented in incident counters | Yes | No | Webhook-only in MVP |
| `incident.warn` | Represented in dashboard incidents/counters | Yes | No | Represented in dashboard incidents/counters | No | No | Observe-only anomaly lifecycle signal |
| `protection.warn` | No | No | No | Reflected indirectly through Protect behavior and visible incidents | Yes | Yes | Protect warning signal, emitted once per protect condition episode |
| `protection.clamp_started` | No | No | No | Clamp is visible in Protect behavior, not as a separate incident state | Yes | Yes | Protect-only, emitted once when clamp first begins affecting traffic |
| `protection.block` | No | No | No | Reflected indirectly through Protect behavior and visible incidents | Yes | Yes | Protect-only; reasons `cap_breach`, `cooldown_active`, `fail_closed` |
| `incident.resolved` | Represented in dashboard incident history/state | Yes | No | Represented in dashboard incident history/state | Yes | Yes | Shared lifecycle closure signal |
| `webhook.delivery_failed` | Not represented by incident counters | No | No | Not represented by incident counters | No | Yes, if webhook is enabled | Persistent transport-health signal |
| `webhook.test` | UI result only | Test only | No | UI result only | Test only | No | Explicit user action, outside normal alert reporting |

## Protect Reporting Rules

- `incident.warn`
  - emitted once when a fresh observe-mode incident episode opens
  - not emitted again while the same incident row is merely being updated
  - a fresh `incident.warn` is emitted again only after the prior episode has gone cold and a new incident row is opened
  - the incident row `evidence.count` tracks repeated matches within that same active episode
  - dashboard incident cards count open rows, not `evidence.count`

- `protection.warn`
  - emitted by the decision engine for Protect warn outcomes
  - reasons: `near_cap`, `retry_storm`, `loop_suspect`, `token_explosion`
  - dedupe: once per protect condition episode
- `protection.clamp_started`
  - emitted only when auto clamp is enabled and first begins affecting traffic
  - dedupe: once per clamp activation episode
- `protection.block`
  - emitted when Protect actually prevents traffic
  - reasons:
    - `cap_breach`
    - `cooldown_active`
    - `fail_closed`
  - `detail_reason` carries the more specific source when needed:
    - `req_cap_breach`
    - `tok_cap_breach`
    - `decision_timeout`
    - `decision_unavailable`
  - dedupe:
    - `cap_breach`: once when the new block episode starts
    - `cooldown_active`: once when cooldown begins actively blocking requests
    - `fail_closed`: once per actual fallback exercise

## Raw Webhook Scope (MVP)

- Policy-gap does not have a separate in-app notification surface.
- Current runtime transport for `policy_gap.detected` remains webhook-only.
- If a future customer-facing policy-gap route is added, prefer email over another dashboard banner/toast.

Current implementation:
- The raw project webhook is machine-readable and sends the canonical Rheonic payload.
- The Alerts page shows a sample raw webhook payload for inspection and copying, but does not expose a payload editor.
- `webhook.test` validates URL/reachability only; it does not use a custom body editor.

Sample raw webhook payload (`protection.warn`):

```json
{
  "event": "protection.warn",
  "project_id": "proj_123",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "environment": "staging",
  "reason": "retry_storm",
  "requests_60s": 12,
  "tokens_60s": 640,
  "req_cap": 400,
  "tok_cap": 1700,
  "estimated_next_tokens": 120,
  "apply_clamp_enabled": false,
  "sent_at": "2026-03-17T06:23:20Z",
  "clamp": null
}
```

Deferred to V2:
- Telegram integration
- Slack integration
- provider-specific message templates
- webhook-backed adapter presets
- per-event templates
- custom request headers
- custom HTTP methods

## Email Template Catalog

Registry: `app/application/email_templates/registry.py`

- `feedback_submitted`
- `protection_warn`
- `protection_clamp_started`
- `protection_block`
- `incident_resolved`
- `webhook_delivery_failed`

All templates render deterministic `subject`, `html`, and `text`.
