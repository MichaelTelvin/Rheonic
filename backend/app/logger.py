# Shared application logging utilities.
import logging
import os


_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str | None = None) -> None:
    # Configure global logging handlers and levels.
    resolved_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(level=resolved_level, format=_DEFAULT_FORMAT, force=True)


def get_logger(name: str) -> logging.Logger:
    # Return a namespaced logger instance.
    return logging.getLogger(name)
