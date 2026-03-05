# RQ-backed webhook dispatcher.
from __future__ import annotations

from app.application.services.transport_service import TransportService, build_transport_dedupe_key
from app.application.interfaces.webhook_dispatcher import WebhookDispatcher
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.repositories.transport_outbox_repository_impl import TransportOutboxRepositoryImpl
from app.infrastructure.jobs.transport_job import enqueue_outbox_delivery


class RQWebhookDispatcher(WebhookDispatcher):
    # Writes webhook deliveries to outbox and enqueues transport worker jobs.

    def __init__(self, redis_url: str) -> None:
        _ = redis_url
        self._transport = TransportService(
            outbox_repository=TransportOutboxRepositoryImpl(session_factory=DatabaseSessionFactory()),
            enqueue_job=enqueue_outbox_delivery,
        )

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
        # Queue one outbox row; worker applies delivery + retries/backoff policy.
        transport_payload: dict[str, object] = {
            "body": dict(payload),
            "__transport_meta": {
                "override_secret": override_secret,
                "force_send": bool(force_send),
            },
        }
        dedupe_key = build_transport_dedupe_key(
            project_id=project_id,
            kind="webhook",
            event_type=event_type,
            payload=transport_payload,
            destination=override_url,
        )
        self._transport.enqueue(
            project_id=project_id,
            kind="webhook",
            event_type=event_type,
            payload=transport_payload,
            dedupe_key=dedupe_key,
            destination=override_url,
        )
