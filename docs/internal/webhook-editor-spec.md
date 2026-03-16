# Webhook Editor Spec

This document defines the first implementation pass for webhook payload customization.

## Goal

Let users adapt Rheonic webhook bodies to downstream providers without losing the core transport contract or editing immutable system fields.

## Current Constraint

Today a project can configure:
- `webhook_enabled`
- `email_enabled`
- `webhook_url`
- `webhook_secret`

The outgoing webhook body is the event payload emitted by the runtime/API path, wrapped into the shared transport outbox and signed at send time.

There is no persisted payload customization yet.

## Product Decision

The editor should be constrained, not arbitrary.

We want:
- one clear project-level payload customization surface
- a small JSON canvas
- locked system fields
- custom static fields
- a reliable preview/test loop

We do not want:
- freeform code execution
- user-authored scripts
- transport logic branching in the browser
- provider-specific one-off hacks in the core dispatcher

## MVP Data Model

Add one optional project-level field:
- `webhook_payload_template_json`

Shape:
- nullable JSON object
- when `null`, use the current default payload untouched
- when present, render the template into the final webhook request body

Validation:
- object root required
- max serialized size: small and bounded, e.g. `<= 8 KB`
- recursive values limited to JSON primitives / arrays / objects
- string placeholders allowed
- reject dangerous keys like `__proto__`, `constructor`, `prototype`

## Template Model

The editor stores a JSON object template.

Example:

```json
{
  "chat_id": "123456",
  "text": "Rheonic {{event}} for {{project_id}}: {{incident_type}}",
  "metadata": {
    "provider": "{{provider}}",
    "environment": "{{environment}}"
  }
}
```

### Locked Variables

These variables are available for interpolation and are not directly editable as source data:
- `event`
- `project_id`
- `incident_id`
- `incident_type`
- `provider`
- `model`
- `environment`
- `sent_at`
- `resolved_at`
- `resolved_by`
- `reason`
- `requests_60s`
- `tokens_60s`
- `req_cap`
- `tok_cap`
- `destination`
- `status`
- `attempts`
- `max_attempts`
- `last_error_code`
- `last_error_message`

Rules:
- missing variables render as empty strings
- interpolation happens only inside string values
- no expression language in MVP

## Runtime Rendering

Send path:
1. Runtime/API emitter produces the canonical event payload.
2. Dispatcher writes to outbox as usual.
3. Transport worker resolves the project webhook payload template.
4. If template is absent:
   - send canonical payload as-is
5. If template is present:
   - render template against canonical payload
   - send rendered body

Signing:
- HMAC signing still uses the final rendered JSON body bytes.

Destination URL:
- unchanged by the editor

## UI Shape

Location:
- Alerts page, inside the Webhook card, below URL/secret fields

Sections:
1. `Payload format`
   - toggle: `Use custom payload`
2. `Available fields`
   - read-only variable list
3. `Payload editor`
   - JSON textarea/canvas
4. `Preview`
   - rendered sample JSON for the selected event type
5. `Test webhook`
   - uses the current saved-or-draft payload template with `webhook.test`

## UX Rules

- default state shows the canonical payload contract
- custom mode is opt-in
- invalid JSON blocks save
- preview should show validation errors inline
- user should understand that the signing secret still signs the final rendered body

## Event Preview Set

The preview selector should support:
- `incident.warn`
- `incident.block`
- `incident.resolved`
- `policy_gap.detected`
- `webhook.delivery_failed`
- `webhook.test`

Use deterministic example payloads in the UI.

## Testing Plan

### Backend
- save/load template in project settings
- reject invalid template payloads
- render canonical body when template is absent
- render custom body when template exists
- sign rendered body, not canonical body
- `webhook.test` uses the same rendering path

### Frontend
- editor hidden by default
- enabling custom payload reveals canvas + preview
- invalid JSON blocks save
- preview updates for event selector changes
- saved template reloads without visual toggle flicker

### Staging Manual Checks
- default webhook path still works unchanged
- custom template works for:
  - `incident.warn`
  - `incident.block`
  - `incident.resolved`
  - `policy_gap.detected`
  - `webhook.test`
- terminal webhook failure email still triggers for real alert sends
- failed `webhook.test` still does not trigger dashboard delivery banner or failure email

## Non-Goals

- separate template per event
- custom headers/body signing strategy
- custom auth schemes
- custom retry policy per webhook
- provider catalog integrations
