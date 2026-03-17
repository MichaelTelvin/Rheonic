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
| `decision.warn` | webhook | `ProtectService._enqueue_warn_webhook` | `event`, `project_id`, `provider`, `model`, `environment`, `reason`, `requests_60s`, `tokens_60s`, `req_cap`, `tok_cap`, `estimated_next_tokens`, `apply_clamp_enabled`, `clamp`, `sent_at` | Project webhook URL (`projects.webhook_url`) | Protect only |
| `incident.block` | webhook + email | `ProtectService._enqueue_block_notifications` | `event`, `project_id`, `provider`, `model`, `environment`, `incident_type`, `reason`, `requests_60s`, `tokens_60s`, `req_cap`, `tok_cap`, `blocked_until`, `retry_after_seconds`, `sent_at` | Project webhook URL + owning user account email | Protect only |
| `incident.warn` | webhook + email | `IncidentManager._enqueue_detection_notifications` | `event`, `project_id`, `incident_id`, `incident_type`, `provider`, `model`, `environment`, `created_at`, `last_seen_at`, `sent_at`, `evidence` | Project webhook URL + owning user account email | Protect: non-`cap_breach`, non-`near_cap` incident opens. Observe: all incident opens, including `cap_breach` and `near_cap`. |
| `incident.resolved` | webhook + email | `DetectIncidentsService` and `AutoCloseIncidentsService` resolved enqueue paths | `event`, `project_id`, `incident_id`, `incident_type`, `resolved_by`, `resolved_at`, `created_at`, `last_seen_at`, `provider`, `model`, `environment`, `sent_at` | Project webhook URL + owning user account email | Protect only |
| `policy_gap.detected` | webhook | `IngestEventService._detect_policy_gap_if_needed` | `event_type`, `project_id`, `provider`, `model`, `first_seen_at`, `sent_at` | Project webhook URL | Protect only; first-seen `(project, provider, model)` |
| `webhook.delivery_failed` | email | transport worker terminal webhook failure hook | `project_id`, `event_type`, `destination`, `status`, `attempts`, `max_attempts`, `last_error_code`, `last_error_message`, `updated_at` | Owning user account email | Protect only; only when webhook is enabled and terminal failure is reached |
| `webhook.test` | webhook | `POST /api/v1/projects/{project_id}/webhook/test` | `event`, `project_id`, `sent_at` | Project webhook URL or test override URL | Mode-independent; excluded from delivery-failure banner/email |
| `feedback.submitted` | email | `POST /api/v1/feedback` | `message`, `email`, `user_id`, `user_email`, `project_id`, `page`, `mode`, `timestamp`, `app_version` | Feedback report address (`Settings.feedback_report_email`) | Mode-independent (authenticated feedback action) |

## Delivery Policy Matrix

### Policy principles
- Protect notifications are transport-agnostic: choosing email vs webhook must not remove core safety information.
- In-app notifications are intentionally narrow and reserved for signals not already represented well by durable dashboard state.
- `incident.resolved` is part of transport delivery, but not a general in-app notification.
- Email is protect-only for customer-facing alerts and feedback/internal workflows.
- Webhook may later gain an optional verbose event stream, but the default core alert set stays aligned with email.
- Protect notification bodies should include action context when the emitter can assert it reliably; do not fabricate action data when the decision/incident relationship is ambiguous.
- In `Protect`, `near_cap` remains a visible incident in the dashboard, but its transport path is the preflight `decision.warn` event rather than a separate `incident.warn` lifecycle alert.
- In `Observe`, `near_cap` and `cap_breach` incident opens emit the raw `incident.warn` webhook because there is no preflight decision transport.

### Core alert tiers
- Core lifecycle alerts:
  - `incident.warn`
  - `incident.block`
  - `incident.resolved`
  - `webhook.delivery_failed`
- Auxiliary signals:
  - `policy_gap.detected`
  - `decision.warn`
  - `feedback.submitted`
  - `webhook.test`

### Matrix

| Event / Condition | Observe dashboard state | Observe in-app | Observe webhook | Observe email | Protect dashboard state | Protect in-app | Protect webhook | Protect email | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `feedback.submitted` | No | No | No | Internal only | No | No | No | Internal only | Product/admin workflow, not customer-facing alerting |
| `policy_gap.detected` | Not represented in incident counters | No | No by default | No | Not represented in incident counters | No | Yes | No | No dedicated in-app surface; webhook-only for now |
| `decision.warn` | No dedicated notification surface | No | No | No | Reflected indirectly via protect behavior; not a standalone dashboard notification | No | No by default | No | Keep out of the default alert set; verbose webhook stream may be added later as an explicit opt-in |
| `incident.warn` | Represented in dashboard incidents/counters | No | No by default | No | Represented in dashboard incidents/counters | No | Yes | Yes | Core protect lifecycle alert for non-`near_cap` ingest opens |
| `incident.block` | Represented in dashboard incidents/counters | No | No by default | No | Represented in dashboard incidents/counters | No | Yes | Yes | Core protect lifecycle alert; include block reason/action when deterministic |
| `incident.resolved` | Represented in dashboard incident history/state | No | No by default | No | Represented in dashboard incident history/state | No | Yes | Yes | No general in-app notification; manual resolve already has direct UI feedback |
| `webhook.delivery_failed` | Not represented by incident counters | Yes | No | No | Not represented by incident counters | Yes | No | Yes, if webhook is enabled | Persistent transport-health signal; protect user should learn if webhook delivery is broken |
| `webhook.test` | UI result only | No | Test only | No | UI result only | No | Test only | No | Explicit user action, outside normal notification policy |

## Protect Content Rules

- For protect transports, the default payload set is the same across email and webhook for lifecycle alerts.
- Notification bodies should include action context only when it is reliable:
  - `incident.block`: action is deterministically `block`
  - preflight `near_cap`-origin warning paths may report `warn`
  - ingest-origin warning incidents should not overclaim a protect action if the system cannot prove one
- If action context is ambiguous, omit it or mark it as best-effort/latest context rather than asserting a false causal mapping.

## Raw Webhook Scope (MVP)

- Policy-gap does not have a separate in-app notification surface.
- Current runtime transport for `policy_gap.detected` remains webhook-only.
- If a future customer-facing policy-gap route is added, prefer email over another dashboard banner/toast.

Current implementation:
- The raw project webhook is machine-readable and sends the canonical Rheonic payload.
- The Alerts page shows a sample raw webhook payload for inspection and copying, but does not expose a payload editor.
- `webhook.test` validates URL/reachability only; it does not use a custom body editor.
- Any legacy stored `webhook_payload_template_json` is ignored for live raw webhook delivery.

Sample raw webhook payload (`incident.warn`):

```json
{
  "event": "incident.warn",
  "project_id": "proj_123",
  "incident_id": "inc_456",
  "incident_type": "retry_storm",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "environment": "staging",
  "created_at": "2026-03-17T06:21:00Z",
  "last_seen_at": "2026-03-17T06:23:14Z",
  "sent_at": "2026-03-17T06:23:20Z",
  "evidence": {
    "failure_count": 5,
    "threshold_count": 5,
    "requests_60s": 12,
    "tokens_60s": 640
  }
}
```

Deferred to V2:
- Telegram integration
- Slack integration
- provider-specific message templates
- webhook-backed adapter presets
- per-event templates
- custom request headers beyond the signing secret
- custom HTTP methods

## Email Template Catalog

Registry: `app/application/email_templates/registry.py`

- `feedback_submitted`
- `incident_warn`
- `incident_block`
- `incident_resolved`
- `webhook_delivery_failed`

All templates render deterministic `subject`, `html`, and `text`.
