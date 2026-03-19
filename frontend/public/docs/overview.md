# Rheonic Overview

Rheonic helps you monitor and control LLM runtime risk across your application. It records provider activity, detects common failure patterns, and can optionally block or warn before a risky call goes out.

## What You Can Do
- Track live request and token volume by project.
- Review incidents such as `near_cap`, `retry_storm`, `loop_suspect`, and `token_explosion`.
- Enable Protect mode to warn or block when limits are about to be crossed.
- Send alert notifications by email or webhook.
- Instrument OpenAI, Anthropic, and Google calls from Node or Python.

## Core Concepts
- **Project**: your main workspace in Rheonic. Metrics, incidents, keys, protect settings, and alerts are configured per project.
- **Ingest key**: the credential your SDK uses to send telemetry and request protect decisions.
- **Observe mode**: records telemetry and incidents without changing runtime behavior.
- **Protect mode**: evaluates requests before provider calls and can return `allow`, `warn`, or `block`.
- **Provider scope**: counters and protect decisions are tracked separately per provider inside a project.

## Product Areas
- **Dashboard**: live requests, tokens, incident summary, protect decisions, and delivery failures.
- **Projects**: create, select, and delete projects.
- **Keys**: create, rotate, and revoke ingest keys.
- **Protect**: configure request caps, token caps, fail mode, and auto clamp.
- **Alerts**: configure email and webhook delivery for protect events.
- **Incidents**: filter, inspect, and resolve open incidents.

## Roadmap Snapshot
We are actively expanding Rheonic beyond the current protect and incident set. Planned improvements include:
- model downgrade actions for safer fallback behavior,
- cached-response workflows for degraded or protected paths,
- stronger rate-limiting controls,
- additional policy actions and tuning presets,
- deeper analytics and longer-term trend views.

## Recommended Reading
1. `Quickstart` for first-time setup.
2. `Protect Mode` before enabling enforcement.
3. `Alerts` if you want email or webhook delivery.
4. `Roadmap` for upcoming product direction.
5. `API Reference` for endpoint-level details.
