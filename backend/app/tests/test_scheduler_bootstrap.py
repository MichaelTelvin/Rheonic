from __future__ import annotations

from dataclasses import dataclass

from app.workers.scheduler_bootstrap import RecurringJob, ensure_recurring_jobs


@dataclass
class _FakeJob:
    id: str


class _FakeScheduler:
    def __init__(self) -> None:
        self.jobs: list[_FakeJob] = []
        self.scheduled_calls: list[dict[str, object]] = []

    def get_jobs(self):  # noqa: ANN201 - mirrors rq-scheduler API
        return list(self.jobs)

    def schedule(self, **kwargs):  # noqa: ANN003, ANN201 - mirrors rq-scheduler API
        self.scheduled_calls.append(kwargs)
        self.jobs.append(_FakeJob(id=str(kwargs["id"])))


def test_scheduler_bootstrap_is_idempotent() -> None:
    scheduler = _FakeScheduler()
    jobs = [
        RecurringJob(
            job_id="llmtbg_auto_close_incidents",
            func_path="app.infrastructure.jobs.auto_close_incidents_job.auto_close_incidents",
            interval_seconds=60,
        ),
        RecurringJob(
            job_id="llmtbg_purge_old_events",
            func_path="app.infrastructure.jobs.purge_events_job.purge_old_events",
            interval_seconds=86400,
        ),
    ]

    first_scheduled = ensure_recurring_jobs(scheduler=scheduler, jobs=jobs)
    second_scheduled = ensure_recurring_jobs(scheduler=scheduler, jobs=jobs)

    assert first_scheduled == 2
    assert second_scheduled == 0
    assert [job.id for job in scheduler.jobs] == [job.job_id for job in jobs]

    for call in scheduler.scheduled_calls:
        assert call["result_ttl"] == 3600
        if "failure_ttl" in call:
            assert call["failure_ttl"] == 86400
