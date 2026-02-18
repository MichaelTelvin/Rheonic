# Application service for ingest key management.
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.application.input_validation import sanitize_key_label
from app.application.interfaces.ingest_key_repository import IngestKeyRepository
from app.application.interfaces.project_repository import ProjectRepository
from app.domain.models.ingest_key import IngestKey
from app.domain.models.project import Project
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

    def resolve_project_id(self, plaintext_key: str, allow_unowned_project: bool = False) -> str | None:
        # Resolve active key to project id.
        project = self.resolve_project(plaintext_key=plaintext_key, allow_unowned_project=allow_unowned_project)
        if project is None:
            return None
        return project.id

    def resolve_project(self, plaintext_key: str, allow_unowned_project: bool = False) -> Project | None:
        # Resolve active key to project.
        key_hash = hash_key(plaintext_key)
        key = self._ingest_key_repository.get_active_by_hash(key_hash)
        if key is None:
            return None
        project = self._project_repository.get_project(key.project_id)
        if project is None:
            return None
        if project.user_id is None and not allow_unowned_project:
            return None
        return project

    def list_keys(self, project_id: str, user_id: str) -> list[IngestKey]:
        # List keys for an existing project.
        self._ensure_project_owned_by_user(project_id=project_id, user_id=user_id)
        return self._ingest_key_repository.list_by_project(project_id)

    def create_key(self, project_id: str, name: str, user_id: str) -> tuple[IngestKey, str]:
        # Create a new active key and return plaintext once.
        self._ensure_project_owned_by_user(project_id=project_id, user_id=user_id)
        normalized_name = sanitize_key_label(name)
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

    def revoke_key(self, key_id: str, user_id: str) -> IngestKey:
        # Revoke an existing key.
        existing = self._ingest_key_repository.get_by_id(key_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="key not found")
        self._ensure_project_owned_by_user(project_id=existing.project_id, user_id=user_id)
        if existing.status == "revoked":
            return existing
        revoked = self._ingest_key_repository.revoke_key(key_id=key_id, revoked_at=datetime.now(timezone.utc))
        if revoked is None:
            raise HTTPException(status_code=404, detail="key not found")
        return revoked

    def rotate_key(self, key_id: str, user_id: str) -> tuple[IngestKey, str]:
        # Rotate key by revoking existing one and creating new one for same project.
        existing = self._ingest_key_repository.get_by_id(key_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="key not found")
        self._ensure_project_owned_by_user(project_id=existing.project_id, user_id=user_id)
        self.revoke_key(key_id, user_id=user_id)
        return self.create_key(project_id=existing.project_id, name=existing.name, user_id=user_id)

    def _ensure_project_owned_by_user(self, project_id: str, user_id: str) -> None:
        # Validate project ownership.
        project = self._project_repository.get_project(project_id)
        if project is None or project.user_id != user_id:
            raise HTTPException(status_code=404, detail="project not found")
