# Interface for enqueuing project webhook deliveries.
from abc import ABC, abstractmethod


class WebhookDispatcher(ABC):
    # Abstraction for webhook dispatch enqueue behavior.

    @abstractmethod
    def enqueue(
        self,
        project_id: str,
        payload: dict[str, object],
        event_type: str,
        *,
        override_url: str | None = None,
        force_send: bool = False,
    ) -> None:
        # Enqueue a webhook delivery job for project/event.
        raise NotImplementedError
