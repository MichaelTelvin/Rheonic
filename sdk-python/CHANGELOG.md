# Changelog

All notable changes to `rheonic-sdk` will be documented in this file.

## Unreleased

- Publish-ready changelog entries will be added here for the next release.

## 0.1.0b7

### Changed
- `RHEONICBlockedError` now exposes structured block feedback for apps and agents: `reason`, `retry_after_seconds`, `blocked_until`, `trace_id`, `request_id`, and `snapshot`.
- Fail-closed protect fallback now reports `reason="fail_closed"` instead of the generic `decision_unavailable` on blocked requests.

## 0.1.0b6

### Added
- Initial public beta release of the Rheonic Python SDK.
- Manual event capture and protect preflight client APIs.
- OpenAI, Anthropic, and Google provider instrumentation helpers.
- Structured SDK logging with trace correlation.

### Changed
- Packaging is scoped to the `src/rheonic` distribution contents for clean wheel and sdist output.

### Docs
- Added install, configuration, and minimal integration guidance for beta users.
