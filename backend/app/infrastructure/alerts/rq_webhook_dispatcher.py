# RQ-backed webhook dispatcher.
from __future__ import annotations

from redis import Redis
from rq import Queue, Retry

from app.application.interfaces.webhook_dispatcher import WebhookDispatcher


class RQWebhookDispatcher(WebhookDispatcher):
    # Enqueues webhook delivery jobs onto the llmtbg RQ queue.

    def __init__(self, redis_url: str) -> None:
        self._queue = Queue("llmtbg", connection=Redis.from_url(redis_url))

    def enqueue(self, project_id: str, payload: dict[str, object], event_type: str) -> None:
        # Queue one webhook job with retry/backoff policy.
        self._queue.enqueue(
            "app.infrastructure.jobs.webhook_job.send_project_webhook",
            kwargs={
                "project_id": project_id,
                "payload": payload,
                "event_type": event_type,
            },
            retry=Retry(max=3, interval=[5, 20, 60]),
            result_ttl=3600,
            failure_ttl=86400,
        )
