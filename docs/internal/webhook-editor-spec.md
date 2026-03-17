# Integrations V2 Note

The webhook payload editor is deferred from MVP.

## MVP

- `Email`
  - Protect mode only
  - unchanged

- `Webhook`
  - available in Observe and Protect
  - sends the canonical Rheonic payload only
  - no custom body editor in the Alerts page
  - `webhook.test` validates delivery reachability only

## V2

Planned follow-up work:
- `Integrations` section in Alerts
- webhook-backed Telegram adapter
- webhook-backed Slack adapter
- small provider-specific message template editors

The intent is to keep the raw webhook machine-readable and move human-facing provider shaping into dedicated integration adapters.
