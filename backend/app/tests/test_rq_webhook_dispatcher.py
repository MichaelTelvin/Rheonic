from redis import Redis
from rq.job import Job
from rq.utils import import_attribute

from app.config import Settings
from app.infrastructure.alerts.rq_webhook_dispatcher import RQWebhookDispatcher
from app.infrastructure.jobs.webhook_job import send_project_webhook


class _CaptureQueue:
    def __init__(self) -> None:
        self.func = None
        self.kwargs = None

    def enqueue(self, func, **kwargs):
        self.func = func
        self.kwargs = kwargs
        return None


def test_webhook_dispatcher_enqueues_importable_job_callable() -> None:
    dispatcher = RQWebhookDispatcher(redis_url="redis://localhost:6379/15")
    capture = _CaptureQueue()
    dispatcher._queue = capture  # type: ignore[assignment]

    dispatcher.enqueue(project_id="p1", payload={"event": "webhook.test"}, event_type="webhook.test")

    assert capture.func is send_project_webhook
    assert capture.kwargs is not None
    assert capture.kwargs["kwargs"]["project_id"] == "p1"

    resolved = import_attribute(f"{capture.func.__module__}.{capture.func.__name__}")
    assert resolved is send_project_webhook

    redis_url = Settings().redis_url
    job = Job.create(
        func=capture.func,
        kwargs={
            "project_id": "p1",
            "payload": {"event": "webhook.test"},
            "event_type": "webhook.test",
        },
        connection=Redis.from_url(redis_url),
    )
    assert job.func is send_project_webhook
