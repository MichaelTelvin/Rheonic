# Notification Catalog

This catalog is derived from current backend emitters and transport code.

## Transport Path (single path)
- Emitters call `WebhookDispatcher.enqueue(...)` or `TransportService.enqueue(...)`.
- `RQWebhookDispatcher` writes to `transport_outbox` via `TransportService`.
- Worker job `process_outbox_delivery` sends webhook/email asynchronously and updates outbox state.
- Dashboard delivery-failure card reads aggregated outbox statuses (`failed`/`dead`) via `GET /api/v1/metrics/delivery-failures`.

## Event Catalog

| Event type | Kind | Emitter(s) | Payload schema (current keys) | Intended recipient(s) | Mode gating |
|---|---|---|---|---|---|
| `decision.warn` | webhook | `ProtectService._enqueue_warn_webhook` | `event`, `project_id`, `provider`, `reason`, `requests_60s`, `tokens_60s`, `req_cap`, `tok_cap`, `estimated_next_tokens`, `apply_clamp_enabled`, `clamp`, `sent_at` | Project webhook URL (`projects.webhook_url`) | Protect only |
| `incident.block` | webhook | `ProtectService._enqueue_block_webhook` | `event`, `project_id`, `provider`, `incident_type`, `reason`, `requests_60s`, `tokens_60s`, `req_cap`, `tok_cap`, `sent_at` | Project webhook URL | Protect only |
| `incident.warn` | webhook | `IncidentManager._enqueue_detection_webhook` | `event`, `project_id`, `incident_id`, `incident_type`, `provider`, `created_at`, `last_seen_at`, `sent_at`, `evidence` | Project webhook URL | Protect only; only non-`cap_breach`, non-`near_cap` incident opens |
| `incident.resolved` | webhook | `DetectIncidentsService._enqueue_incident_resolved_webhook`, `AutoCloseIncidentsService._enqueue_incident_resolved_webhook` | `event`, `project_id`, `incident_id`, `incident_type`, `resolved_by`, `resolved_at`, `created_at`, `last_seen_at`, `provider`, `model`, `environment`, `sent_at` | Project webhook URL | Protect only |
| `policy_gap.detected` | webhook | `IngestEventService._detect_policy_gap_if_needed` | `event_type`, `project_id`, `provider`, `model`, `first_seen_at`, `sent_at` | Project webhook URL | Protect only; first-seen `(project, provider, model)` |
| `webhook.test` | webhook | `POST /api/v1/projects/{project_id}/webhook/test` | `event`, `project_id`, `sent_at` | Project webhook URL or test override URL | Mode-independent |
| `feedback.submitted` | email | `POST /api/v1/feedback` | `message`, `email`, `user_id`, `user_email`, `project_id`, `page`, `mode`, `timestamp`, `app_version` | Feedback report address (`Settings.feedback_report_email`) unless outbox destination override | Mode-independent (authenticated feedback action) |

## Email Template Catalog

Registry: `app/application/email_templates/registry.py`

- `feedback_submitted`
- `decision_warn`
- `incident_warn`
- `incident_block`
- `incident_resolved`
- `policy_gap_detected`
- `webhook_delivery_failed` (template available; not yet emitted by a dedicated runtime event)

All templates render deterministic `subject`, `html`, and `text`.
