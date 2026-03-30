# Alerts

Rheonic can notify you about incident lifecycle and Protect reporting events. Alerts are configured per project from the `Alerts` page.

## Delivery Channels
- Email to your account email address
- Webhook to your own endpoint

## What You Can Configure
### Email
- turn delivery on or off,
- send notifications to the authenticated account email.
- Email is used only in Protect mode.

### Webhook
- enable or disable the webhook,
- set the destination URL,
- inspect a sample payload before wiring your consumer,
- send a test event before relying on production delivery.

## Event Types
### Observe mode
- `incident.warn`
- `incident.resolved`
- `policy_gap.detected` by webhook only after the project already has baseline provider/model history

### Protect mode
- `protection.clamp_started`
- `protection.block`
- `incident.warn`
- `incident.block`
- `incident.resolved`
- `policy_gap.detected` by webhook only after the project already has baseline provider/model history
- `webhook.delivery_failed` by email when webhook delivery reaches a terminal failure

### Explicit test event
- `webhook.test`

Protect email and Protect webhook carry the same core reporting semantics. Webhook remains machine-readable; email is the operator-facing route.

## Testing Webhooks
Use the `Test webhook` action from the dashboard. Rheonic queues a test payload and shows the result as a toast. `Last live webhook delivery` reflects real runtime delivery only, not test sends.

Raw webhooks always send the canonical Rheonic payload in MVP. Human-facing provider formatting such as Telegram or Slack is planned as a V2 integration layer rather than a raw webhook editor.

Sample payload for `protection.clamp_started`:

```json
{
  "event": "protection.clamp_started",
  "project_id": "proj_123",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "environment": "staging",
  "reason": "token_clamp",
  "requests_60s": 12,
  "tokens_60s": 640,
  "req_cap": 400,
  "tok_cap": 1700,
  "estimated_next_tokens": 120,
  "sent_at": "2026-03-17T06:23:20Z",
  "clamp": {
    "recommended_max_output_tokens": 64,
    "applied": false
  }
}
```

Field notes:
- `event`: webhook event type
- `project_id`: Rheonic project identifier
- `provider`: provider associated with the decision/report
- `model`: model associated with the request when available
- `environment`: environment associated with the request when available
- `reason`: Protect enforcement reason such as `token_clamp` or `req_cap_breach`
- `requests_60s`: rolling request count for the scoped `(project, provider)`
- `tokens_60s`: rolling token count for the scoped `(project, provider)`
- `req_cap`: configured request cap when present
- `tok_cap`: configured token cap when present
- `estimated_next_tokens`: predictive token estimate used by the decision engine when available
- `clamp`: clamp recommendation or applied clamp context when relevant
- `sent_at`: when Rheonic queued the webhook payload

## Delivery Behavior
- API and runtime paths enqueue deliveries asynchronously.
- Delivery happens out of band through the transport worker.
- Retries and terminal failures are tracked.
- Dashboard delivery-failure metrics are based on outbox delivery state.

## Recommended Setup
1. Enable email so someone on the team receives failures quickly.
2. Configure a webhook for Slack, PagerDuty, or your own incident workflow.
3. In Observe mode, webhook is the incident lifecycle stream.
4. In Protect mode, email and webhook share the same core Protect reporting semantics.
5. Test both channels before enabling Protect mode on production traffic.
6. Watch delivery failures in the dashboard after rollout.
