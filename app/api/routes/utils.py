from fastapi import APIRouter

from app.api.errors import UNAVAILABLE_RESPONSE
from app.api.schemas import ConfigResponse
from app.core.config import settings

router = APIRouter(prefix="/utils", tags=["utils"])


@router.get("/health-check/")
async def health_check() -> bool:
    return True


@router.get("/config", response_model=ConfigResponse, responses=UNAVAILABLE_RESPONSE)
def read_config() -> ConfigResponse:
    """Which sign-in methods this deployment offers (public, no secrets)."""
    return ConfigResponse(
        password_login=settings.ENABLE_PASSWORD_LOGIN,
        google_login=bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET),
        google_client_id=settings.GOOGLE_CLIENT_ID,
    )
