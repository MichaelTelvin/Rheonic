"""Run rq-scheduler for the rheonic queue."""
from __future__ import annotations

from redis import Redis
from rq_scheduler import Scheduler

from app.config import Settings
from app.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    settings = Settings()
    connection = Redis.from_url(settings.redis_url)
    interval_seconds = max(int(settings.rq_scheduler_interval_seconds), 1)
    scheduler = Scheduler(queue_name=settings.rq_queue_name, connection=connection, interval=interval_seconds)
    logger.info("RQ scheduler started", extra={"queue": settings.rq_queue_name, "interval_seconds": interval_seconds})
    scheduler.run()


if __name__ == "__main__":
    main()
