from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Literal

from app.domain.models.transport_outbox import TransportOutbox


class TransportOutboxRepository(ABC):
    @abstractmethod
    def create_or_get_deduped(
        self,
        *,
        project_id: str,
        kind: Literal["webhook", "email"],
        event_type: str,
        destination: str | None,
        subject: str | None,
        template: str | None,
        payload: dict[str, object],
        dedupe_key: str,
        max_attempts: int,
        now: datetime,
    ) -> tuple[TransportOutbox, bool]:
        raise NotImplementedError

    @abstractmethod
    def claim_for_send(self, *, outbox_id: str, now: datetime) -> TransportOutbox | None:
        raise NotImplementedError

    @abstractmethod
    def mark_delivered(self, *, outbox_id: str, now: datetime) -> TransportOutbox | None:
        raise NotImplementedError

    @abstractmethod
    def mark_failed(
        self,
        *,
        outbox_id: str,
        now: datetime,
        error_code: str,
        error_message: str,
        next_attempt_at: datetime | None,
        dead: bool,
    ) -> TransportOutbox | None:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, outbox_id: str) -> TransportOutbox | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_terminal_by_project_kind(
        self,
        *,
        project_id: str,
        kind: Literal["webhook", "email"],
        exclude_event_types: tuple[str, ...] = (),
        since: datetime | None = None,
    ) -> TransportOutbox | None:
        raise NotImplementedError

    @abstractmethod
    def count_failed_or_dead_by_project_kind(
        self,
        *,
        project_id: str,
        kind: Literal["webhook", "email"],
        exclude_event_types: tuple[str, ...] = (),
        since: datetime | None = None,
    ) -> int:
        raise NotImplementedError
