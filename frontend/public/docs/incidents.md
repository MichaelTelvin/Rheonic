# Incidents

Incidents are the main way Rheonic surfaces risky runtime behavior. They are created from ingested events and appear in the `Incidents` page for the selected project.

## Incident Types
- `block`: Protect blocked a request because a configured request or token cap was already breached.
- `retry_storm`: failed attempts are repeating fast enough to suggest an unhealthy retry loop; retry state by itself does not count as a failure.
- `loop_suspect`: a rapid consecutive sequence with the same request signature suggests the app is stuck in a loop. Failed steps still count, and detection is suppressed when traffic looks highly concurrent.
- `token_explosion`: request-context size is unusually large or growing sharply for the same request signature. Detection is also suppressed when traffic looks highly concurrent.

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
- In Protect mode, behavioral incidents still open from ingest, and Protect can also open a `block` incident when it enforces a hard limit.

## Manual Resolution
Use the `Resolve` action in the `Incidents` page or call the resolve API endpoint. Resolved incidents stay visible when you filter for resolved or all incidents.

## What to Look At First
- repeated incidents from one provider,
- repeated `block` incidents,
- new `retry_storm` or `loop_suspect` patterns after a deploy,
- repeated incidents paired with webhook delivery failures.

## Operational Tip
If you are tuning Protect mode, compare the `Incidents` page with the dashboard's protect decision counters. That helps distinguish ingest-based behavioral incidents from preflight enforcement outcomes.
