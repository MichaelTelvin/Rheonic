# Public runtime config endpoint.
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_settings

router = APIRouter()


class PublicConfigOut(BaseModel):
    # Safe public config values for frontend.
    public_contact_email: str


@router.get("/public-config", response_model=PublicConfigOut)
def get_public_config(settings: Settings = Depends(get_settings)) -> PublicConfigOut:
    # Return public-facing config values.
    return PublicConfigOut(public_contact_email=(settings.public_contact_email or "").strip())
