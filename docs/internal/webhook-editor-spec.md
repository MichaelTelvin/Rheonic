# Webhook Editor Spec

## Goal

Keep webhook customization simple:
- one project-level JSON object field for the user's provider-specific body
- no template language
- no preview builder
- no editable Rheonic metadata

Rheonic adds its own metadata automatically at delivery time under a protected `rheonic` object.

## Product Rules

- The Alerts page always shows the custom webhook body editor.
- The editor contains one textarea only.
- The textarea accepts a JSON object only.
- The UI shows placeholder sample text, not prefilled data.
- The UI does not expose Rheonic metadata fields or placeholder tokens.
- `webhook.test` uses the current draft-or-saved JSON body.

## Stored Data

Persist one optional field on each project:
- `webhook_payload_template_json`

Despite the legacy name, this field now stores only the user's raw JSON object.

Validation:
- root must be a JSON object
- reject forbidden keys such as `__proto__`, `constructor`, `prototype`
- reject `rheonic` at the top level because it is reserved
- keep the existing size bound

## Delivery Behavior

When no custom JSON exists:
- send the canonical Rheonic payload unchanged

When custom JSON exists:
1. load the stored JSON object
2. append `rheonic: {...canonical metadata...}`
3. sign the final rendered JSON body
4. deliver it

The user JSON is not interpolated and is not rewritten except for the protected `rheonic` attachment.

## UI Shape

Routing card:
- email toggle
- recipient display
- webhook toggle
- webhook URL
- webhook secret
- webhook test/save actions

Custom payload card:
- one textarea labeled `Webhook body`
- concise helper copy
- no secondary controls
- no preview panel

## Manual Checks

- save valid custom JSON
- reject malformed JSON
- reject non-object JSON
- reject a top-level `rheonic` key
- `webhook.test` sends the current draft JSON plus protected Rheonic metadata
- real lifecycle webhook sends append the same protected metadata

## Non-Goals

- templating
- placeholder tokens
- per-event payload variants
- provider-specific UI presets
- custom headers beyond the webhook signing secret
