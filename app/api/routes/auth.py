"""OIDC sign-in.

The SPA obtains a Google ID token and posts it here. The endpoint is the
sign-in call: it validates the token, resolves (or creates) the local account
and returns its public profile, so the UI learns immediately whether the
account is allowed. The same ID token is then usable as a bearer credential on
every authenticated route (see `app/api/deps.py`).
"""

from fastapi import APIRouter

from app.api.deps import ConnDep
from app.api.errors import api_responses
from app.api.mappers import to_user_response
from app.api.schemas import GoogleTokenRequest, UserResponse
from app.core.google import verify_google_id_token
from app.domain.errors import ErrorCode
from app.services import users as user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/google",
    response_model=UserResponse,
    responses=api_responses(ErrorCode.EMAIL_NOT_ALLOWED, ErrorCode.INACTIVE_USER),
)
def login_with_google(payload: GoogleTokenRequest, conn: ConnDep) -> UserResponse:
    """Validate a Google ID token and return the local account it identifies."""
    identity = verify_google_id_token(payload.id_token)
    user = user_service.login_with_google(conn=conn, identity=identity)
    return to_user_response(user)
