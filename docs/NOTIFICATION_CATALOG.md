# Notification Catalog

This catalog reflects the implemented notification contract.

## Transport Path (single path)
- Emitters call `WebhookDispatcher.enqueue(...)` or `TransportService.enqueue(...)`.
- `RQWebhookDispatcher` writes to `transport_outbox` via `TransportService`.
- Worker job `process_outbox_delivery` sends webhook/email asynchronously and updates outbox state.
- Dashboard delivery-failure card reads aggregated outbox statuses (`failed`/`dead`) via `GET /api/v1/metrics/delivery-failures`.

## Runtime Event Catalog

| Event type | Kind | Emitter(s) | Payload schema (current keys) | Intended recipient(s) | Mode gating |
|---|---|---|---|---|---|
| `decision.warn` | webhook | `ProtectService._enqueue_warn_webhook` | `event`, `project_id`, `provider`, `reason`, `requests_60s`, `tokens_60s`, `req_cap`, `tok_cap`, `estimated_next_tokens`, `apply_clamp_enabled`, `clamp`, `sent_at` | Project webhook URL (`projects.webhook_url`) | Protect only |
| `incident.block` | webhook + email | `ProtectService._enqueue_block_notifications` | `event`, `project_id`, `provider`, `incident_type`, `reason`, `requests_60s`, `tokens_60s`, `req_cap`, `tok_cap`, `sent_at` | Project webhook URL + owning user account email | Protect only |
| `incident.warn` | webhook + email | `IncidentManager._enqueue_detection_notifications` | `event`, `project_id`, `incident_id`, `incident_type`, `provider`, `created_at`, `last_seen_at`, `sent_at`, `evidence` | Project webhook URL + owning user account email | Protect only; only non-`cap_breach`, non-`near_cap` incident opens |
| `incident.resolved` | webhook + email | `DetectIncidentsService` and `AutoCloseIncidentsService` resolved enqueue paths | `event`, `project_id`, `incident_id`, `incident_type`, `resolved_by`, `resolved_at`, `created_at`, `last_seen_at`, `provider`, `model`, `environment`, `sent_at` | Project webhook URL + owning user account email | Protect only |
| `policy_gap.detected` | webhook | `IngestEventService._detect_policy_gap_if_needed` | `event_type`, `project_id`, `provider`, `model`, `first_seen_at`, `sent_at` | Project webhook URL | Protect only; first-seen `(project, provider, model)` |
| `webhook.delivery_failed` | email | transport worker terminal webhook failure hook | `project_id`, `event_type`, `destination`, `status`, `attempts`, `max_attempts`, `last_error_code`, `last_error_message`, `updated_at` | Owning user account email | Protect only; only when webhook is enabled and terminal failure is reached |
| `webhook.test` | webhook | `POST /api/v1/projects/{project_id}/webhook/test` | `event`, `project_id`, `sent_at` | Project webhook URL or test override URL | Mode-independent |
| `feedback.submitted` | email | `POST /api/v1/feedback` | `message`, `email`, `user_id`, `user_email`, `project_id`, `page`, `mode`, `timestamp`, `app_version` | Feedback report address (`Settings.feedback_report_email`) | Mode-independent (authenticated feedback action) |

## Delivery Policy Matrix

### Policy principles
- Protect notifications are transport-agnostic: choosing email vs webhook must not remove core safety information.
- In-app notifications are intentionally narrow and reserved for signals not already represented well by durable dashboard state.
- `incident.resolved` is part of transport delivery, but not a general in-app notification.
- Email is protect-only for customer-facing alerts and feedback/internal workflows.
- Webhook may later gain an optional verbose event stream, but the default core alert set stays aligned with email.
- Protect notification bodies should include action context when the emitter can assert it reliably; do not fabricate action data when the decision/incident relationship is ambiguous.

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
| `policy_gap.detected` | Not represented in incident counters | Yes | No by default | No | Not represented in incident counters | Yes | Yes | No | Distinct operator signal; low urgency, no email |
| `decision.warn` | No dedicated notification surface | No | No | No | Reflected indirectly via protect behavior; not a standalone dashboard notification | No | No by default | No | Keep out of the default alert set; verbose webhook stream may be added later as an explicit opt-in |
| `incident.warn` | Represented in dashboard incidents/counters | No | No by default | No | Represented in dashboard incidents/counters | No | Yes | Yes | Core protect lifecycle alert |
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

## Deferred Scope

- Webhook body editor: approved as a follow-up after the notification engine is operationally complete.
- The editor should be constrained:
  - immutable system fields remain locked
  - users may shape the surrounding payload/envelope
  - preview/test delivery should be required

## Email Template Catalog

Registry: `app/application/email_templates/registry.py`

- `feedback_submitted`
- `incident_warn`
- `incident_block`
- `incident_resolved`
- `webhook_delivery_failed`

All templates render deterministic `subject`, `html`, and `text`.
