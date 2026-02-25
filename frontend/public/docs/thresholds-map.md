# Thresholds Map

## Baseline Gate
- `baseline_gate_min_windows`: minimum baseline samples required before baseline-relative detector checks are allowed.
- `baseline_gate_min_baseline_req`: minimum baseline requests value used by gate readiness.
- `baseline_gate_min_baseline_tok`: minimum baseline tokens value used by gate readiness.
- `baseline_gate_early_abs_req_60s`: early absolute requests threshold that can trigger during warm-up.
- `baseline_gate_early_abs_tok_60s`: early absolute tokens threshold that can trigger during warm-up.
- When it applies: ingest-time anomaly detection for all modes.

## Detector Thresholds
- `detectors_req_spike_ratio_low`: minimum request ratio to baseline for request-spike signal.
- `detectors_req_spike_delta_low`: minimum request delta to baseline for request-spike signal.
- `detectors_tok_spike_ratio_low`: minimum token ratio to baseline for token-spike signal.
- `detectors_tok_spike_delta_low`: minimum token delta to baseline for token-spike signal.
- Rule: baseline-ready path requires ratio AND delta; warm-up path only allows early-absolute trigger.
- Stubs (not implemented yet): retry storm, loop suspect, token explosion.
- When it applies: ingest-time anomaly detection after counters/baseline update.

## Escalation Thresholds
- `incident_escalation_window_medium_seconds`: window length used to evaluate low->medium promotion.
- `incident_escalation_window_high_seconds`: window length used to evaluate medium->high and guarded low->high.
- `incident_escalation_min_hits_medium`: minimum hits in medium window required for medium promotion.
- `incident_escalation_min_hits_high`: minimum hits in high window required for high promotion.
- `incident_escalation_score_threshold_medium`: minimum score sum in medium window for medium promotion.
- `incident_escalation_score_threshold_high`: minimum score sum in high window for high promotion.
- `incident_escalation_ttl_seconds`: Redis TTL for escalation hit history.
- Hit scoring meaning:
  - mild hit: score 1 (`ratio >= incident_escalation_score_ratio_low`)
  - moderate hit: score 2 (`ratio >= incident_escalation_score_ratio_medium`)
  - severe hit: score 3 (`ratio >= incident_escalation_score_ratio_high`)
- Guard: low->high requires at least one severe hit (`incident_escalation_high_score_required`).
- When it applies: only when an incident already exists and new matching signals arrive.

## Protect Thresholds
- `protect_max_req_per_min`: hard request cap; decision is `block` on exceed.
- `protect_max_tok_per_min`: hard token cap; decision is `block` on exceed.
- `protect_near_cap_factor`: predictive near-cap threshold; decision is `warn` only.
- `protect_block_cooldown_seconds`: cooldown duration after block reasons that set cooldown.
- `protect_fail_mode`: SDK behavior when decision endpoint is unavailable (`open` allows, `closed` blocks).
- When it applies: protect preflight only (`/api/v1/protect/decision`) and only when protect is enabled.

## Incident Lifecycle Windows
- `incident_dedup_window_seconds`: open-incident dedup window for fingerprint updates vs new row creation.
- `incident_auto_close_seconds`: inactivity cooldown before open incident auto-resolves.
- `auto_close_run_interval_seconds`: scheduler cadence for running auto-close job.
- When it applies: all runtime incidents regardless of provider, scoped per `(project_id, provider)`.
