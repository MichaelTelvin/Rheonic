# Thresholds Map

This document explains how runtime thresholds interact in practice so you can tune with confidence.

## Rolling 60s Counters
- `rolling_window_seconds`: logical window for realtime counters (`requests_60s`, `tokens_60s`).
- `rolling_window_ms`: millisecond form of the same window.
- `rolling_counter_ttl_seconds`: Redis TTL for per-second rolling buckets.
- `baseline_counter_ttl_seconds`: Redis TTL for baseline sample history.
- Scope: counters are tracked per `(project_id, provider)`.
- Dashboard behavior: project totals are aggregated across providers unless a provider filter is applied.
- When it applies: every ingest event and every protect decision read.

## Baseline Sampling
- `baseline_window_count`: number of recent baseline windows used for baseline median calculation.
- A baseline "window" means one persisted sample of the project/provider rolling counters at ingest time.
- Baseline updates are frozen while matching open incidents exist for that same `(project_id, provider)` scope.
- When it applies: ingest pipeline before detector evaluation.

## BaselineGate Readiness
- `baseline_gate_min_windows`: minimum baseline sample count required before baseline-relative checks are allowed.
- `baseline_gate_min_baseline_req`: minimum baseline requests level required for readiness.
- `baseline_gate_min_baseline_tok`: minimum baseline tokens level required for readiness.
- Gate outputs:
- `baseline_ready`: whether ratio+delta detector checks may run.
- `reason`: readiness/warm-up explanation.
- When it applies: immediately before detector evaluation.

## Warm-up Behavior (Early Absolute Triggers)
- `baseline_gate_early_abs_req_60s`: request absolute threshold that can trigger during warm-up.
- `baseline_gate_early_abs_tok_60s`: token absolute threshold that can trigger during warm-up.
- Purpose: catch obvious burn spikes even before a baseline is mature.
- If these are not crossed during warm-up, ratio-based spikes are intentionally suppressed.
- When it applies: only while `BaselineGate` is not baseline-ready.

## Detector Rules (Ratio + Delta)
### Request spike detector
- `detectors_req_spike_ratio_low`: minimum request ratio to baseline.
- `detectors_req_spike_delta_low`: minimum request delta to baseline.
- Rule: signal emits only when both ratio and delta thresholds are met (baseline-ready path).

### Token spike detector
- `detectors_tok_spike_ratio_low`: minimum token ratio to baseline.
- `detectors_tok_spike_delta_low`: minimum token delta to baseline.
- Rule: signal emits only when both ratio and delta thresholds are met (baseline-ready path).

### Evidence payload expectations
- Signals/incidents store evidence including:
- current counters
- baseline counters
- ratio and delta
- gate warm-up/readiness state
- thresholds used
- whether early-absolute path fired

### Future detector placeholders
- Retry storm detector (stub)
- Loop suspect detector (stub)
- Token explosion detector (stub)

## Severity and Escalation Rules
### Base severity mapping thresholds
- `incident_severity_ratio_low`
- `incident_severity_ratio_medium`
- `incident_severity_ratio_high`
- These thresholds map ratio intensity to initial severity levels.

### Escalation hit scoring
- `incident_escalation_score_ratio_low`: mild-hit lower bound.
- `incident_escalation_score_ratio_medium`: moderate-hit lower bound.
- `incident_escalation_score_ratio_high`: severe-hit lower bound.
- `incident_escalation_high_score_required`: guard score required for low->high jump.
- `incident_escalation_hit_list_max_entries`: cap for stored hit history list.

### Escalation windows and promotion criteria
- `incident_escalation_window_medium_seconds`: time window for low->medium promotion evaluation.
- `incident_escalation_window_high_seconds`: time window for medium->high / guarded low->high evaluation.
- `incident_escalation_min_hits_medium`: minimum hits needed for medium promotion.
- `incident_escalation_min_hits_high`: minimum hits needed for high promotion.
- `incident_escalation_score_threshold_medium`: minimum cumulative score for medium promotion.
- `incident_escalation_score_threshold_high`: minimum cumulative score for high promotion.
- `incident_escalation_ttl_seconds`: TTL for escalation hit cache.

## Incident Lifecycle Windows
- `incident_dedup_window_seconds`: dedup window; matching open incident is updated instead of creating a new row.
- `incident_auto_close_seconds`: inactivity cooldown before open incidents are auto-resolved.
- `auto_close_run_interval_seconds`: scheduler cadence for running auto-close job.
- `scheduler_default_result_ttl_seconds`: result TTL for scheduled jobs.
- `scheduler_default_failure_ttl_seconds`: failure TTL for scheduled jobs.
- When it applies:
- dedup during open/update flow
- auto-close in background scheduler path

## Protect Thresholds and Decisioning
### Hard caps
- `protect_max_req_per_min` (project setting): hard request cap for block.
- `protect_max_tok_per_min` (project setting): hard token cap for block.

### Predictive near-cap
- `protect_near_cap_factor`: near-cap factor used for proactive warn path.
- Requires `input_tokens_estimate` (SDK) and optionally `max_output_tokens`.
- This path is warn-only and has lower priority than block conditions.

### Cooldown and failure mode
- `protect_block_cooldown_seconds`: cooldown duration after block reasons that set cooldown.
- `protect_fail_mode` (project setting): SDK behavior when decision call fails (`open` or `closed`).
- `protect_decision_timeout_ms` (project setting): client-side protect decision timeout.

### Decision order (current)
- cooldown active -> block
- hard cap exceeded (`req_limit` / `tok_limit`) -> block
- incident severity high -> block
- incident severity medium -> warn
- predictive near-cap -> warn
- else -> allow

## Webhook Triggers
- `webhook_retry_max_attempts`: max retry attempts for failed webhook delivery.
- `webhook_retry_intervals_seconds`: retry backoff schedule.
- `webhook_result_ttl_seconds`: TTL for successful delivery records.
- `webhook_failure_ttl_seconds`: TTL for failed delivery records.
- `webhook_timeout_connect_seconds`
- `webhook_timeout_read_seconds`
- `webhook_timeout_write_seconds`
- `webhook_timeout_pool_seconds`
- `webhook_max_error_chars`: truncation limit for stored delivery error strings.
- `webhook_allow_private_hosts`: host safety override.

Webhook event timings:
- high incident open -> `incident.high`
- escalation to high -> `incident.high` (`source=escalation`)
- manual resolve -> `incident.resolved` (`resolved_by=manual`)
- auto resolve -> `incident.resolved` (`resolved_by=auto`)
- first-seen `(provider, model)` tuple -> `policy_gap.detected` (recorded once per tuple; no incident created)

## Tuning Checklist
### If you get false positives
1. Increase `detectors_req_spike_delta_low` / `detectors_tok_spike_delta_low` first.
2. Increase `detectors_req_spike_ratio_low` / `detectors_tok_spike_ratio_low` second.
3. Increase `baseline_gate_min_windows` if baseline is too noisy early.
4. Raise `baseline_gate_early_abs_req_60s` / `baseline_gate_early_abs_tok_60s` if warm-up catches too much.
5. Raise escalation thresholds (`incident_escalation_min_hits_*`, `incident_escalation_score_threshold_*`) if severity jumps too quickly.

### If you miss real spikes
1. Lower `detectors_req_spike_delta_low` / `detectors_tok_spike_delta_low` first.
2. Lower `detectors_req_spike_ratio_low` / `detectors_tok_spike_ratio_low` second.
3. Lower warm-up absolute thresholds (`baseline_gate_early_abs_req_60s`, `baseline_gate_early_abs_tok_60s`) if early spikes are missed.
4. Reduce `baseline_gate_min_windows` only if your traffic is too sparse to become ready.
5. Lower escalation thresholds carefully so repeated hits promote sooner.
