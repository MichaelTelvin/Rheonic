# Application configuration objects.
from dataclasses import dataclass

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class AppConfig:
    default_log_format: str = "%(asctime)s %(levelname)s %(name)s %(message)s"
    rolling_window_seconds: int = 60
    rolling_window_ms: int = rolling_window_seconds * 1000
    rolling_counter_ttl_seconds: int = 600
    baseline_counter_ttl_seconds: int = 3600
    rate_limit_window_seconds: int = 60
    incident_type_burn_spike: str = "burn_spike"
    incident_type_request_spike: str = "request_spike"
    incident_type_policy_gap: str = "policy_gap"
    incident_severity_ratio_low: float = 2.0
    incident_severity_ratio_medium: float = 5.0
    incident_severity_ratio_high: float = 10.0
    incident_escalation_score_ratio_low: float = 4.0
    incident_escalation_score_ratio_medium: float = 6.0
    incident_escalation_score_ratio_high: float = 10.0
    incident_escalation_high_score_required: int = 3
    incident_escalation_hit_list_max_entries: int = 2000
    default_incident_escalation_window_medium_seconds: int = 300
    default_incident_escalation_window_high_seconds: int = 120
    default_incident_escalation_min_hits_medium: int = 2
    default_incident_escalation_min_hits_high: int = 2
    default_incident_escalation_score_threshold_medium: int = 4
    default_incident_escalation_score_threshold_high: int = 6
    default_incident_escalation_ttl_seconds: int = 360
    baseline_gate_min_windows: int = 5
    baseline_gate_min_baseline_req: float = 5.0
    baseline_gate_min_baseline_tok: float = 500.0
    baseline_gate_early_abs_req_60s: int = 300
    baseline_gate_early_abs_tok_60s: int = 20000
    detectors_req_spike_ratio_low: float = 4.0
    detectors_req_spike_delta_low: float = 50.0
    detectors_tok_spike_ratio_low: float = 4.0
    detectors_tok_spike_delta_low: float = 2000.0
    protect_near_cap_factor: float = 0.8
    protect_action_counter_ttl_seconds: int = 3600
    webhook_retry_max_attempts: int = 3
    webhook_retry_intervals_seconds: tuple[int, int, int] = (5, 20, 60)
    webhook_result_ttl_seconds: int = 3600
    webhook_failure_ttl_seconds: int = 86400
    webhook_timeout_connect_seconds: float = 2.0
    webhook_timeout_read_seconds: float = 5.0
    webhook_timeout_write_seconds: float = 5.0
    webhook_timeout_pool_seconds: float = 5.0
    webhook_max_error_chars: int = 240
    webhook_secret_prefix: str = "enc:v1:"
    webhook_secret_default_fallback_key: str = "llmtbg-webhook-secret-default"
    scheduler_default_result_ttl_seconds: int = 3600
    scheduler_default_failure_ttl_seconds: int = 86400
    purge_interval_seconds: int = 24 * 60 * 60
    name_max_length: int = 80
    email_max_length: int = 320
    name_validation_pattern: str = r"^[A-Za-z0-9 _.-]+$"
    email_validation_pattern: str = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    control_chars: tuple[str, str, str] = ("\r", "\n", "\t")


app_config = AppConfig()


class Settings(BaseSettings):
    # Runtime settings container for the backend service.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LLMTokenBurnGuard API"
    api_prefix: str = "/api"
    app_env: str = "dev"
    jwt_secret: str = ""
    jwt_alg: str = "HS256"
    jwt_expires_min: int = 60
    jwt_refresh_expires_min: int = 10080
    cors_origins: str = ""
    database_url: str = ""
    redis_url: str = ""
    idempotency_ttl_seconds: int = 120
    ingest_rate_limit_per_minute: int = 600
    rate_limit_window_seconds: int = app_config.rate_limit_window_seconds
    baseline_window_count: int = 30
    incident_dedup_window_seconds: int = 300
    incident_escalation_window_medium_seconds: int = 300
    incident_escalation_window_high_seconds: int = 120
    incident_escalation_min_hits_medium: int = 2
    incident_escalation_min_hits_high: int = 2
    incident_escalation_score_threshold_medium: int = 4
    incident_escalation_score_threshold_high: int = 6
    incident_escalation_ttl_seconds: int = 360
    baseline_gate_min_windows: int = app_config.baseline_gate_min_windows
    baseline_gate_min_baseline_req: float = app_config.baseline_gate_min_baseline_req
    baseline_gate_min_baseline_tok: float = app_config.baseline_gate_min_baseline_tok
    baseline_gate_early_abs_req_60s: int = app_config.baseline_gate_early_abs_req_60s
    baseline_gate_early_abs_tok_60s: int = app_config.baseline_gate_early_abs_tok_60s
    # Detector thresholds (authoritative); legacy incident_* ratio cutoffs are retained for severity mapping.
    detectors_req_spike_ratio_low: float = app_config.detectors_req_spike_ratio_low
    detectors_req_spike_delta_low: float = app_config.detectors_req_spike_delta_low
    detectors_tok_spike_ratio_low: float = app_config.detectors_tok_spike_ratio_low
    detectors_tok_spike_delta_low: float = app_config.detectors_tok_spike_delta_low
    incident_auto_close_seconds: int = 300
    auto_close_run_interval_seconds: int = 60
    event_retention_days: int = 30
    protect_block_cooldown_seconds: int = 60
    ingest_allow_unowned_project: bool = False
    webhook_allow_private_hosts: bool = False
    webhook_secret_encryption_key: str = ""

    # TODO: Add env-driven database, Redis, auth, and provider settings.
