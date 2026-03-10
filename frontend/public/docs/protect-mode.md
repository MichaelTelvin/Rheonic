# Protect Mode

Protect mode adds a preflight decision before a provider call. It uses recent project activity and your configured limits to decide whether the request should proceed.

## Observe vs Protect
### Observe
- telemetry is recorded,
- incidents can still open,
- provider calls are never blocked by Rheonic,
- no runtime warn or block action is enforced.

### Protect
- telemetry is recorded,
- the preflight can return `allow`, `warn`, or `block`,
- request and token caps are enforced,
- cooldown and other protect signals can prevent a provider call.

## Where to Configure It
Open the `Protect` page in the dashboard for the selected project.

Available settings:
- `Protect enabled`
- `Protect fail mode`
- `Request cap per minute`
- `Token cap per minute`
- `Auto token clamp`

## Decision Outcomes
- `allow`: request proceeds normally.
- `warn`: request proceeds, but the outcome is counted and can trigger notifications.
- `block`: request is denied before the provider call runs.

## What Can Trigger a Block
- request cap breach,
- token cap breach,
- active cooldown after a previous block,
- protect fail mode set to closed when the decision path is unavailable.

## What Can Trigger a Warn
- `near_cap`
- `retry_storm`
- `loop_suspect`
- `token_explosion`

Warn outcomes also appear in the dashboard so the reason for a protected request stays visible.

## Auto Token Clamp
When `Auto token clamp` is enabled, Rheonic can return a recommended lower output token limit in the decision payload. SDKs can apply that value before the provider request is sent.

## Fail Modes
- `open`: if the protect decision is unavailable, allow the request.
- `closed`: if the protect decision is unavailable, block the request.

Use `open` while rolling out. Move to `closed` only when you are confident in backend availability.

## Rollout Guidance
1. Start in Observe mode and confirm traffic is flowing.
2. Configure alerts so warn and block outcomes are visible.
3. Set conservative request and token caps.
4. Enable Protect on one project first.
5. Review incidents, warns, and blocks before wider rollout.

## Provider Scope
Protect counters and decisions are tracked per provider inside each project. This prevents one provider's traffic from contaminating another provider's limits.
