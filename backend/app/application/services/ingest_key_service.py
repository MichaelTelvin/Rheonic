# Application service for ingest key management.
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.application.interfaces.ingest_key_repository import IngestKeyRepository
from app.application.interfaces.project_repository import ProjectRepository
from app.domain.models.ingest_key import IngestKey
from app.logger import get_logger
from app.security.ingest_keys import generate_ingest_key, hash_key, last4

logger = get_logger(__name__)


class IngestKeyService:
    # Handles ingest key creation, lookup, revoke, and rotation.

    def __init__(
        self,
        ingest_key_repository: IngestKeyRepository,
        project_repository: ProjectRepository,
    ) -> None:
        # Initialize service dependencies.
        self._ingest_key_repository = ingest_key_repository
        self._project_repository = project_repository

    def resolve_project_id(self, plaintext_key: str) -> str | None:
        # Resolve active key to project id.
        key_hash = hash_key(plaintext_key)
        key = self._ingest_key_repository.get_active_by_hash(key_hash)
        if key is None:
            return None
        return key.project_id

    def list_keys(self, project_id: str) -> list[IngestKey]:
        # List keys for an existing project.
        self._ensure_project_exists(project_id)
        return self._ingest_key_repository.list_by_project(project_id)

    def create_key(self, project_id: str, name: str) -> tuple[IngestKey, str]:
        # Create a new active key and return plaintext once.
        self._ensure_project_exists(project_id)
        normalized_name = name.strip()
        if not normalized_name:
            raise HTTPException(status_code=422, detail="key name is required")
        plaintext = generate_ingest_key()
        now = datetime.now(timezone.utc)
        key = IngestKey(
            id=str(uuid4()),
            project_id=project_id,
            name=normalized_name,
            key_hash=hash_key(plaintext),
            last4=last4(plaintext),
            status="active",
            created_at=now,
            revoked_at=None,
        )
        created = self._ingest_key_repository.create_key(key)
        return created, plaintext

    def revoke_key(self, key_id: str) -> IngestKey:
        # Revoke an existing key.
        existing = self._ingest_key_repository.get_by_id(key_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="key not found")
        if existing.status == "revoked":
            return existing
        revoked = self._ingest_key_repository.revoke_key(key_id=key_id, revoked_at=datetime.now(timezone.utc))
        if revoked is None:
            raise HTTPException(status_code=404, detail="key not found")
        return revoked

    def rotate_key(self, key_id: str) -> tuple[IngestKey, str]:
        # Rotate key by revoking existing one and creating new one for same project.
        existing = self._ingest_key_repository.get_by_id(key_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="key not found")
        self.revoke_key(key_id)
        return self.create_key(project_id=existing.project_id, name=existing.name)

    def _ensure_project_exists(self, project_id: str) -> None:
        # Validate project existence.
        if self._project_repository.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail="project not found")
