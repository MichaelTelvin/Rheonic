"""Authentication endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/login")
async def login() -> dict[str, str]:
    """Authenticate a user and issue access credentials."""
    # TODO: Add auth provider integration and token issuance.
    return {"status": "ok"}
