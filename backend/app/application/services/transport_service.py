from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Callable, Literal

from app.application.interfaces.transport_outbox_repository import TransportOutboxRepository
from app.config import app_config
from app.logger import generate_span_id, generate_trace_id, get_trace_id


class TransportService:
    def __init__(
        self,
        *,
        outbox_repository: TransportOutboxRepository,
        enqueue_job: Callable[..., None],
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._outbox_repository = outbox_repository
        self._enqueue_job = enqueue_job
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def enqueue(
        self,
        *,
        project_id: str,
        kind: Literal["webhook", "email"],
        event_type: str,
        payload: dict[str, object],
        dedupe_key: str,
        trace_id: str | None = None,
        span_id: str | None = None,
        destination: str | None = None,
        subject: str | None = None,
        template: str | None = None,
        severity: str | None = None,
        provider: str | None = None,
        environment: str | None = None,
    ) -> str:
        if not dedupe_key or not dedupe_key.strip():
            raise ValueError("dedupe_key is required")
        now = self._now_provider()
        normalized_payload: dict[str, object] = dict(payload)
        transport_meta_value = normalized_payload.get("__transport_meta")
        transport_meta = dict(transport_meta_value) if isinstance(transport_meta_value, dict) else {}
        # Preserve one canonical end-to-end trace for the notification chain.
        # Worker jobs should bind to this stored trace instead of inventing a
        # second unrelated request trace for the same notification.
        canonical_trace_id = (get_trace_id() or "").strip()
        if canonical_trace_id:
            transport_meta.setdefault("trace_id", canonical_trace_id)
        if transport_meta:
            normalized_payload["__transport_meta"] = transport_meta
        if severity is not None:
            normalized_payload.setdefault("severity", severity)
        if provider is not None:
            normalized_payload.setdefault("provider", provider)
        if environment is not None:
            normalized_payload.setdefault("environment", environment)

        max_attempts = _max_attempts(kind)
        outbox, created = self._outbox_repository.create_or_get_deduped(
            project_id=project_id,
            kind=kind,
            event_type=event_type,
            destination=destination,
            subject=subject,
            template=template,
            payload=normalized_payload,
            dedupe_key=dedupe_key.strip(),
            max_attempts=max_attempts,
            now=now,
        )
        if created:
            resolved_trace_id = (trace_id or get_trace_id() or generate_trace_id()).strip()
            resolved_span_id = (span_id or generate_span_id()).strip()
            try:
                self._enqueue_job(outbox.id, trace_id=resolved_trace_id, span_id=resolved_span_id)
            except TypeError:
                self._enqueue_job(outbox.id)
        return outbox.id


def build_transport_dedupe_key(
    *,
    project_id: str,
    kind: Literal["webhook", "email"],
    event_type: str,
    payload: dict[str, object],
    destination: str | None = None,
    seed: str | None = None,
) -> str:
    source = {
        "project_id": project_id,
        "kind": kind,
        "event_type": event_type,
        "destination": destination,
        "payload": _dedupe_safe_payload(payload),
        "seed": seed,
    }
    encoded = json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _dedupe_safe_payload(payload: dict[str, object]) -> dict[str, object]:
    sanitized = dict(payload)
    transport_meta_value = sanitized.get("__transport_meta")
    if not isinstance(transport_meta_value, dict):
        return sanitized
    transport_meta = dict(transport_meta_value)
    transport_meta.pop("trace_id", None)
    if transport_meta:
        sanitized["__transport_meta"] = transport_meta
    else:
        sanitized.pop("__transport_meta", None)
    return sanitized


def _max_attempts(kind: Literal["webhook", "email"]) -> int:
    if kind == "webhook":
        return max(int(app_config.webhook_retry_max_attempts), 1)
    return max(int(app_config.email_retry_max_attempts), 1)
