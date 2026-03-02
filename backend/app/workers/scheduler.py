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
    scheduler = Scheduler(queue_name="rheonic", connection=connection, interval=15)
    logger.info("RQ scheduler started", extra={"queue": "rheonic", "interval_seconds": 15})
    scheduler.run()


if __name__ == "__main__":
    main()
