"""Bootstrap recurring RQ scheduler jobs idempotently."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from inspect import signature

from redis import Redis
from rq_scheduler import Scheduler

from app.config import Settings, app_config
from app.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class RecurringJob:
    """Recurring scheduler job definition."""

    job_id: str
    func_path: str
    interval_seconds: int


def ensure_recurring_jobs(
    scheduler: Scheduler,
    jobs: list[RecurringJob],
    *,
    result_ttl_seconds: int = app_config.scheduler_default_result_ttl_seconds,
    failure_ttl_seconds: int = app_config.scheduler_default_failure_ttl_seconds,
) -> int:
    """Ensure recurring jobs exist exactly once, returning newly scheduled count."""
    try:
        existing_ids = {job.id for job in scheduler.get_jobs()}
    except TypeError:
        # Some rq-scheduler versions return tuples when with_times=True.
        existing_ids = {job.id for job, _ in scheduler.get_jobs(with_times=True)}

    scheduled_count = 0
    scheduled_time = datetime.now(timezone.utc)
    schedule_params = signature(scheduler.schedule).parameters
    for job in jobs:
        if job.job_id in existing_ids:
            continue
        schedule_kwargs: dict[str, object] = {
            "scheduled_time": scheduled_time,
            "func": job.func_path,
            "interval": job.interval_seconds,
            "repeat": None,
            "id": job.job_id,
            "result_ttl": result_ttl_seconds,
        }
        if "failure_ttl" in schedule_params:
            schedule_kwargs["failure_ttl"] = failure_ttl_seconds
        scheduler.schedule(
            **schedule_kwargs,
        )
        scheduled_count += 1
    return scheduled_count


def main() -> None:
    """Connect to Redis and bootstrap recurring scheduler jobs."""
    settings = Settings()
    redis_conn = Redis.from_url(settings.redis_url)
    scheduler = Scheduler(queue_name="llmtbg", connection=redis_conn)

    jobs = [
        RecurringJob(
            job_id="llmtbg_auto_close_incidents",
            func_path="app.infrastructure.jobs.auto_close_incidents_job.auto_close_incidents",
            interval_seconds=max(int(settings.auto_close_run_interval_seconds), 1),
        ),
        RecurringJob(
            job_id="llmtbg_purge_old_events",
            func_path="app.infrastructure.jobs.purge_events_job.purge_old_events",
            interval_seconds=app_config.purge_interval_seconds,
        ),
    ]
    scheduled = ensure_recurring_jobs(scheduler=scheduler, jobs=jobs)
    logger.info("Scheduler bootstrap completed", extra={"scheduled": scheduled, "total_jobs": len(jobs)})


if __name__ == "__main__":
    main()
