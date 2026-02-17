# Ingest key repository interface.
from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.models.ingest_key import IngestKey


class IngestKeyRepository(ABC):
    # Abstraction for ingest key persistence and lookup.

    @abstractmethod
    def list_by_project(self, project_id: str) -> list[IngestKey]:
        # Return keys for the given project.
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, key_id: str) -> IngestKey | None:
        # Return one key by id.
        raise NotImplementedError

    @abstractmethod
    def get_active_by_hash(self, key_hash: str) -> IngestKey | None:
        # Return active key for a hash value.
        raise NotImplementedError

    @abstractmethod
    def create_key(self, key: IngestKey) -> IngestKey:
        # Persist a new ingest key.
        raise NotImplementedError

    @abstractmethod
    def revoke_key(self, key_id: str, revoked_at: datetime) -> IngestKey | None:
        # Mark key revoked and set revoked timestamp.
        raise NotImplementedError
