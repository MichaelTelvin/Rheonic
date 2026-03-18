"""Run rq-scheduler for the rheonic queue."""
from __future__ import annotations

from redis import Redis
from rq_scheduler import Scheduler

from app.config import Settings
from app.logger import build_log_extra, configure_logging, generate_trace_id, get_logger

logger = get_logger(__name__)


def main() -> None:
    settings = Settings()
    configure_logging(service_name="scheduler", level=settings.log_level)
    connection = Redis.from_url(settings.redis_url)
    interval_seconds = max(int(settings.rq_scheduler_interval_seconds), 1)
    scheduler = Scheduler(queue_name=settings.rq_queue_name, connection=connection, interval=interval_seconds)
    logger.info(
        "RQ scheduler started",
        extra=build_log_extra(
            event="scheduler_started",
            metadata={"queue": settings.rq_queue_name, "interval_seconds": interval_seconds},
            trace_id=generate_trace_id(),
        ),
    )
    scheduler.run()


if __name__ == "__main__":
    main()
