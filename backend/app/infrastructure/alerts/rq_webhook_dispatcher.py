# RQ-backed webhook dispatcher.
from __future__ import annotations

from redis import Redis
from rq import Queue, Retry

from app.application.interfaces.webhook_dispatcher import WebhookDispatcher
from app.config import app_config
from app.infrastructure.jobs.webhook_job import send_project_webhook


class RQWebhookDispatcher(WebhookDispatcher):
    # Enqueues webhook delivery jobs onto the rheonic RQ queue.

    def __init__(self, redis_url: str) -> None:
        self._queue = Queue("rheonic", connection=Redis.from_url(redis_url))

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
            retry=Retry(max=app_config.webhook_retry_max_attempts, interval=list(app_config.webhook_retry_intervals_seconds)),
            result_ttl=app_config.webhook_result_ttl_seconds,
            failure_ttl=app_config.webhook_failure_ttl_seconds,
        )
