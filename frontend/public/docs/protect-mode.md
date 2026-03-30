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
- cooldown and cap breaches can prevent a provider call,
- behavioral protect signals remain warn-only.

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

`token_explosion` can come from a large request-context size, a cap-relative spike, or a sharp growth step once the request-context has already become meaningfully large. The SDK computes one request-side token-explosion signal before the provider call and sends that same signal into ingest, so protect and observe evaluate the same pattern. Defaults are tuned conservatively for agentic workflows, and growth-only detection is ignored until the current request-context reaches `1800`; after that, a two-step pattern like `1100 -> 1900` can trigger. Growth-only detection is also suppressed when request volume suggests concurrency.

`loop_suspect` is based on a rapid consecutive repeated sequence for the same signature, including failed steps. It is suppressed when request volume suggests concurrency instead of one looping sequence.

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
