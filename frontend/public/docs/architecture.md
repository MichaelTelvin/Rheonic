# Rheonic Architecture

This page gives a product-level view of how Rheonic fits into your application. Use the flow charts for the full request path, then use the API reference when you need exact endpoints.

## System Flow
1. Your app sends an instrumented provider call or a manual telemetry event.
2. The SDK can request a protect decision before the provider call.
3. The provider call runs if the decision is `allow` or `clamp`.
4. Rheonic ingests the event and updates project metrics.
5. Incident detectors evaluate the event and open or update incidents when needed.
6. Dashboard views, alerts, and delivery metrics are updated from the resulting state.

## Main Runtime Components
- **SDKs**: capture telemetry and request protect decisions.
- **Protect service**: evaluates request and token limits before provider execution.
- **Ingest pipeline**: accepts events, normalizes token usage, and updates rolling counters.
- **Incident engine**: turns detector output into incidents that can be reviewed and resolved.
- **Transport worker**: delivers webhook and email notifications asynchronously.
- **Dashboard**: shows metrics, incidents, protect outcomes, and delivery status for the selected project.

## Scope Model
- Projects are the top-level customer boundary in the product.
- Within a project, counters, incidents, and protect decisions are separated by provider.
- Dashboard metrics aggregate across providers by default and can be filtered down to one provider.

## Data Flow
### Protect path
- SDK calls `POST /api/v1/protect/decision`.
- Rheonic evaluates current provider-scoped counters and protect settings.
- The response tells the SDK to `allow`, `clamp`, or `block`.

### Telemetry path
- SDK or custom integration calls `POST /api/v1/events`.
- Rheonic records the event and updates rolling request and token counters.
- Incident detection runs against the event and current state.

### Notification path
- Protect or incident events are queued for delivery.
- Webhook and email delivery happen asynchronously.
- Delivery failures are exposed in dashboard metrics.

## Flow Charts
Use the chart viewer for visual references:
- `Incident Flow` shows how ingest leads to counters, detectors, incidents, and notifications.
- `Protect Flow` shows how preflight decisions are evaluated before provider execution.
