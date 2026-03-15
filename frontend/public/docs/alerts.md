# Alerts

Rheonic can notify you when protect events occur. Alerts are configured per project from the `Alerts` page.

## Delivery Channels
- Email to your account email address
- Webhook to your own endpoint

## What You Can Configure
### Email
- turn delivery on or off,
- send notifications to the authenticated account email.

### Webhook
- enable or disable the webhook,
- set the destination URL,
- set or rotate the signing secret,
- send a test event before relying on production delivery.

## Event Types
- Core protect lifecycle alerts:
  - `incident.warn`
  - `incident.block`
  - `incident.resolved`
  - `webhook.delivery_failed` by email when webhook delivery reaches a terminal failure
- Additional webhook-only signals:
  - `decision.warn`
  - `policy_gap.detected`
- Explicit test event:
  - `webhook.test`

Protect emails are incident-centric and use the same core lifecycle set as protect webhooks. `decision.warn` remains a webhook stream event rather than a standalone email alert. `webhook.test` is available regardless of mode.

## Testing Webhooks
Use the `Test webhook` action from the dashboard. Rheonic queues a test payload and updates the last delivery status after the worker attempts delivery.

## Delivery Behavior
- API and runtime paths enqueue deliveries asynchronously.
- Delivery happens out of band through the transport worker.
- Retries and terminal failures are tracked.
- Dashboard delivery-failure metrics are based on outbox delivery state.

## Recommended Setup
1. Enable email so someone on the team receives failures quickly.
2. Configure a webhook for Slack, PagerDuty, or your own incident workflow.
3. Treat email and webhook as equivalent core protect transports; the difference is routing, not missing safety information.
4. Test both channels before enabling Protect mode on production traffic.
5. Watch delivery failures in the dashboard after rollout.
