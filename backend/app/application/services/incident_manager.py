from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import uuid4

from app.application.interfaces.incident_repository import IncidentRepository
from app.application.interfaces.webhook_dispatcher import WebhookDispatcher
from app.application.services.transport_service import TransportService, build_transport_dedupe_key
from app.config import app_config
from app.domain.detectors.contracts import Signal
from app.domain.models.incident import Incident
from app.logger import get_logger

logger = get_logger(__name__)


class IncidentManager:
    # Persists and updates incidents from detector signals.

    def __init__(
        self,
        *,
        incident_repository: IncidentRepository,
        incident_dedup_window_seconds: int,
        webhook_dispatcher: WebhookDispatcher | None = None,
        transport_service: TransportService | None = None,
    ) -> None:
        self._incident_repository = incident_repository
        self._incident_dedup_window_seconds = incident_dedup_window_seconds
        self._webhook_dispatcher = webhook_dispatcher
        self._transport_service = transport_service

    def process_signals(
        self,
        *,
        project_id: str,
        provider: str,
        model: str | None,
        environment: str | None,
        now: datetime,
        signals: list[Signal],
        mode: str,
    ) -> None:
        for signal in signals:
            self.process_signal(
                project_id=project_id,
                provider=provider,
                model=model,
                environment=environment,
                now=now,
                signal=signal,
                mode=mode,
            )

    def process_signal(
        self,
        *,
        project_id: str,
        provider: str,
        model: str | None,
        environment: str | None,
        now: datetime,
        signal: Signal,
        mode: str,
    ) -> None:
        # Upsert one incident signal inside the dedup window.
        evidence = dict(signal.evidence)
        evidence["provider"] = provider
        evidence["model"] = model
        evidence["environment"] = environment
        evidence["last_seen_at"] = now.isoformat()
        dedup_after = now - timedelta(
            seconds=_signal_episode_window_seconds(signal, self._incident_dedup_window_seconds)
        )
        open_incident = self._incident_repository.get_open_incident_by_fingerprint(
            project_id=project_id,
            provider=provider,
            fingerprint=signal.fingerprint,
            active_after=dedup_after,
        )
        if open_incident is not None:
            next_count = _int_value(open_incident.evidence.get("count")) + 1
            merged_evidence = {
                **open_incident.evidence,
                **evidence,
                "count": next_count,
            }
            self._incident_repository.update_open_incident_activity(
                incident_id=open_incident.id,
                evidence=merged_evidence,
                last_seen_at=now,
            )
            return

        incident = Incident(
            id=str(uuid4()),
            project_id=project_id,
            provider=provider,
            incident_type=signal.detector,
            status="open",
            created_at=now,
            resolved_at=None,
            evidence={**evidence, "count": 1},
            fingerprint=signal.fingerprint,
            last_seen_at=now,
        )
        self._incident_repository.create_incident(incident=incident)
        self._enqueue_detection_notifications(incident=incident, mode=mode)

    def _enqueue_detection_notifications(self, *, incident: Incident, mode: str) -> None:
        if incident.incident_type == app_config.incident_type_block:
            return
        event_type = "incident.warn"
        template = "incident_warn"
        evidence = _build_webhook_evidence(incident.evidence)
        payload: dict[str, object] = {
            "event": event_type,
            "project_id": incident.project_id,
            "incident_id": incident.id,
            "incident_type": incident.incident_type,
            "provider": incident.provider,
            "model": _string_or_none(incident.evidence.get("model")),
            "environment": _string_or_none(incident.evidence.get("environment")),
            "created_at": incident.created_at.isoformat(),
            "last_seen_at": (incident.last_seen_at.isoformat() if incident.last_seen_at is not None else None),
            "mode": mode,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "evidence": evidence,
        }
        if self._webhook_dispatcher is not None:
            try:
                self._webhook_dispatcher.enqueue(
                    project_id=incident.project_id,
                    payload=payload,
                    event_type=event_type,
                )
            except Exception:
                logger.exception(
                    "Failed to enqueue incident webhook",
                    extra={"incident_id": incident.id},
                )
        if self._transport_service is None:
            return
        try:
            dedupe_key = build_transport_dedupe_key(
                project_id=incident.project_id,
                kind="email",
                event_type=event_type,
                payload=payload,
                seed=incident.id,
            )
            self._transport_service.enqueue(
                project_id=incident.project_id,
                kind="email",
                event_type=event_type,
                payload=payload,
                dedupe_key=dedupe_key,
                template=template,
                provider=incident.provider,
                environment=_string_or_none(incident.evidence.get("environment")),
            )
        except Exception:
            logger.exception(
                "Failed to enqueue incident email",
                extra={"incident_id": incident.id, "event_type": event_type},
            )


def _signal_episode_window_seconds(signal: Signal, fallback_seconds: int) -> int:
    value = signal.episode_window_seconds
    if isinstance(value, int) and value > 0:
        return value
    return max(int(fallback_seconds), 1)


def _int_value(value: object) -> int:
    try:
        return int(cast(int | str, value))
    except (TypeError, ValueError):
        return 0


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _build_webhook_evidence(evidence: dict[str, object]) -> dict[str, object]:
    # Keep detailed detector context nested, but remove fields already
    # promoted to the top level.
    sanitized = dict(evidence)
    for key in ("provider", "model", "environment", "last_seen_at", "reason"):
        sanitized.pop(key, None)
    return sanitized
