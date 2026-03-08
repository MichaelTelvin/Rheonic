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
- `decision.warn`
- `incident.warn`
- `incident.block`
- `incident.resolved`
- `policy_gap.detected`
- `webhook.test`

Some events are only sent in Protect mode. `webhook.test` is available regardless of mode.

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
3. Test both channels before enabling Protect mode on production traffic.
4. Watch delivery failures in the dashboard after rollout.
