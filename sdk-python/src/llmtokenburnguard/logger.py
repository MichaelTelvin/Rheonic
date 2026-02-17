# Shared SDK logging utilities.
import logging
import os

from llmtokenburnguard.config import sdk_config


def configure_logging(level: str | None = None) -> None:
    # Configure SDK-wide logging.
    resolved_level = (level or os.getenv("LLMTOKENBURNGUARD_LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(level=resolved_level, format=sdk_config.default_log_format, force=False)


def get_logger(name: str) -> logging.Logger:
    # Return a namespaced logger instance.
    return logging.getLogger(name)
