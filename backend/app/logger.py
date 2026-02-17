# Shared application logging utilities.
import logging
import os

from app.config import app_config


def configure_logging(level: str | None = None) -> None:
    # Configure global logging handlers and levels.
    resolved_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(level=resolved_level, format=app_config.default_log_format, force=True)


def get_logger(name: str) -> logging.Logger:
    # Return a namespaced logger instance.
    return logging.getLogger(name)
