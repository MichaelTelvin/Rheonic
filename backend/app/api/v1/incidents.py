# Incident query endpoints.
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.application.services.project_service import ProjectService
from app.application.services.detect_incidents_service import DetectIncidentsService
from app.dependencies import get_current_user, get_detect_incidents_service, get_project_service
from app.domain.models.user import User
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class IncidentOut(BaseModel):
    # API response model for incidents.
    id: str
    type: str
    severity: str
    status: str
    created_at: datetime
    resolved_at: datetime | None
    evidence: dict[str, object]


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    project_id: str = Query(..., min_length=1),
    status: str = Query("open"),
    service: DetectIncidentsService = Depends(get_detect_incidents_service),
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> list[IncidentOut]:
    # List incidents for the active project context.
    try:
        project_service.ensure_project_owned_by_user(project_id=project_id, user_id=current_user.id)
        incidents = service.list_incidents(project_id=project_id, status=status)
        logger.debug("Incidents list endpoint called", extra={"project_id": project_id, "status": status})
        return [
            IncidentOut(
                id=incident.id,
                type=incident.incident_type,
                severity=incident.severity,
                status=incident.status,
                created_at=incident.created_at,
                resolved_at=incident.resolved_at,
                evidence=incident.evidence,
            )
            for incident in incidents
        ]
    except HTTPException:
        raise
    except Exception:
        logger.exception("List incidents endpoint failed")
        raise HTTPException(status_code=500, detail="Failed to list incidents")


@router.post("/{incident_id}/resolve")
def resolve_incident(
    incident_id: str,
    service: DetectIncidentsService = Depends(get_detect_incidents_service),
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    # Resolve an incident and clear its dedupe lock.
    try:
        incident = service.get_incident(incident_id=incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        project_service.ensure_project_owned_by_user(project_id=incident.project_id, user_id=current_user.id)
        resolved = service.resolve_incident(incident_id=incident_id)
        if resolved is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        logger.info("Incident resolved via API", extra={"incident_id": incident_id})
        return {"status": "resolved"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Resolve incident endpoint failed", extra={"incident_id": incident_id})
        raise HTTPException(status_code=500, detail="Failed to resolve incident")
