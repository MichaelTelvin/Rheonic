# SDK configuration defaults.
from dataclasses import dataclass


@dataclass(frozen=True)
class SDKConfig:
    default_base_url: str = "http://localhost:8000"
    default_environment: str = "dev"
    default_flush_interval_s: float = 1.0
    default_max_queue_size: int = 1000
    default_flush_timeout_s: float = 0.5
    default_request_timeout_s: float = 1.0
    default_protect_fail_mode: str = "open"
    internal_protect_decision_timeout_ms: int = 100
    default_protect_report_timeout_min_s: float = 0.1
    retry_delay_min_s: float = 0.2
    retry_delay_max_s: float = 0.4
    default_log_format: str = "%(asctime)s %(levelname)s %(name)s %(message)s"
    default_tokenizer_encoding: str = "cl100k_base"
    token_estimate_chars_per_token: int = 4
    supported_providers: tuple[str, ...] = ("openai", "anthropic", "google")


sdk_config = SDKConfig()
