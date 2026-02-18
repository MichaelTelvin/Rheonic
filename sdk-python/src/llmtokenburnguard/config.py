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
    default_protect_decision_timeout_ms: int = 100
    default_protect_fail_mode: str = "open"
    retry_delay_min_s: float = 0.2
    retry_delay_max_s: float = 0.4
    default_log_format: str = "%(asctime)s %(levelname)s %(name)s %(message)s"


sdk_config = SDKConfig()
