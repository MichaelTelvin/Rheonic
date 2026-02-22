# RQ-backed webhook dispatcher.
from __future__ import annotations

from redis import Redis
from rq import Queue, Retry

from app.application.interfaces.webhook_dispatcher import WebhookDispatcher
from app.infrastructure.jobs.webhook_job import send_project_webhook


class RQWebhookDispatcher(WebhookDispatcher):
    # Enqueues webhook delivery jobs onto the llmtbg RQ queue.

    def __init__(self, redis_url: str) -> None:
        self._queue = Queue("llmtbg", connection=Redis.from_url(redis_url))

    def enqueue(
        self,
        project_id: str,
        payload: dict[str, object],
        event_type: str,
        *,
        override_url: str | None = None,
        override_secret: str | None = None,
        force_send: bool = False,
    ) -> None:
        # Queue one webhook job with retry/backoff policy.
        self._queue.enqueue(
            send_project_webhook,
            kwargs={
                "project_id": project_id,
                "payload": payload,
                "event_type": event_type,
                "override_url": override_url,
                "override_secret": override_secret,
                "force_send": force_send,
            },
            retry=Retry(max=3, interval=[5, 20, 60]),
            result_ttl=3600,
            failure_ttl=86400,
        )
