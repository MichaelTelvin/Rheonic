# Incidents

Incidents are the main way Rheonic surfaces risky runtime behavior. They are created from ingested events and appear in the `Incidents` page for the selected project.

## Incident Types
- `near_cap`: traffic is approaching a configured request or token cap.
- `cap_breach`: traffic has crossed a hard request or token cap.
- `retry_storm`: failed attempts are repeating fast enough to suggest an unhealthy retry loop; retry state by itself does not count as a failure.
- `loop_suspect`: a rapid consecutive sequence with the same request signature suggests the app is stuck in a loop. Failed steps still count, and detection is suppressed when traffic looks highly concurrent.
- `token_explosion`: request-context size is large, near a cap-driven threshold, or doubling once it has already become meaningfully large. Rheonic evaluates the same request-side signal in protect and observe so warn decisions and incidents stay aligned. By default, growth-only detection is ignored until the current request-context reaches `2500`, and then a two-step pattern like `1300 -> 2600` can trigger. Growth-only detection is suppressed when traffic looks highly concurrent.

## Where to Review Incidents
Open `Incidents` in the dashboard. You can filter by:
- provider,
- status,
- incident type.

## Incident Lifecycle
1. Rheonic detects a qualifying pattern from ingested events.
2. An incident opens for the matching project and provider scope.
3. Repeat detections during the same active incident episode update the existing incident instead of creating a new one.
4. Once that detector episode has gone cold, the next clearly separated trigger opens a fresh incident row and can emit a fresh `incident.warn`.
5. The incident can be resolved manually, or auto-resolved after inactivity.

## Observe and Protect Behavior
- In Observe mode, incidents still open and appear in the dashboard.
- In Protect mode, incidents still open, and protect outcomes can also trigger notifications.

## Manual Resolution
Use the `Resolve` action in the `Incidents` page or call the resolve API endpoint. Resolved incidents stay visible when you filter for resolved or all incidents.

## What to Look At First
- repeated incidents from one provider,
- spikes in `cap_breach` or `near_cap`,
- new `retry_storm` or `loop_suspect` patterns after a deploy,
- repeated incidents paired with webhook delivery failures.

## Operational Tip
If you are tuning Protect mode, compare the `Incidents` page with the dashboard's protect decision counters. That helps distinguish event-based incidents from preflight warn or block outcomes.
