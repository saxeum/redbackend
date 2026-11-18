"""Google OIDC sign-in.

The SPA opens `/api/v1/auth/google/start`. The backend sets a short-lived state
cookie, redirects to Google, and receives the authorization code on `/auth`.
The callback exchanges the code (with PKCE and the server-side client secret),
resolves the local account, issues our own access token, and redirects to the
SPA with the token in the URL fragment.
"""

import secrets
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.api.deps import ConnDep
from app.api.errors import api_responses
from app.api.mappers import to_user_response
from app.api.schemas import GoogleTokenRequest, UserResponse
from app.core import security
from app.core.config import settings
from app.core.google import (
    authorization_url,
    create_pkce_pair,
    exchange_code_for_id_token,
    verify_google_id_token,
)
from app.domain.errors import (
    DomainError,
    ErrorCode,
    InvalidOperation,
)
from app.services import users as user_service

router = APIRouter(prefix="/auth", tags=["auth"])
root_router = APIRouter(tags=["auth"])

OAUTH_COOKIE = "google_oauth"
OAUTH_COOKIE_MAX_AGE = 600


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


@router.get("/google/start")
def google_start() -> RedirectResponse:
    """Begin the authorization-code flow with Google."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise InvalidOperation(ErrorCode.GOOGLE_LOGIN_DISABLED)

    state = secrets.token_urlsafe(32)
    verifier, challenge = create_pkce_pair()
    response = RedirectResponse(
        authorization_url(state=state, code_challenge=challenge),
        status_code=302,
    )
    response.set_cookie(
        OAUTH_COOKIE,
        f"{state}:{verifier}",
        max_age=OAUTH_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.FASTAPI_ENV != "development",
        path="/",
    )
    return response


def _frontend_redirect(*, suffix: str) -> RedirectResponse:
    return RedirectResponse(
        f"{settings.FRONTEND_HOST.rstrip('/')}{suffix}", status_code=302
    )


def _error_redirect(reason: str) -> RedirectResponse:
    response = _frontend_redirect(suffix=f"/login?google_error={reason}")
    response.delete_cookie(OAUTH_COOKIE, path="/")
    return response


@root_router.get("/auth", include_in_schema=False)
def google_callback(
    request: Request,
    conn: ConnDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Handle Google's redirect: validate state, exchange the code, issue a token."""
    if error:
        return _error_redirect("denied")

    cookie = request.cookies.get(OAUTH_COOKIE)
    if not code or not state or not cookie or ":" not in cookie:
        return _error_redirect("failed")

    expected_state, verifier = cookie.split(":", 1)
    if not secrets.compare_digest(state, expected_state):
        return _error_redirect("failed")

    try:
        id_token = exchange_code_for_id_token(code=code, code_verifier=verifier)
        identity = verify_google_id_token(id_token)
        user = user_service.login_with_google(conn=conn, identity=identity)
        access_token = security.create_access_token(
            user.id,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
    except DomainError as exc:
        reason = {
            ErrorCode.EMAIL_NOT_ALLOWED: "not_allowed",
            ErrorCode.INACTIVE_USER: "inactive",
            ErrorCode.GOOGLE_ACCOUNT_TAKEN: "conflict",
            ErrorCode.INVALID_TOKEN: "invalid",
        }.get(exc.code, "failed")
        return _error_redirect(reason)

    response = _frontend_redirect(
        suffix=f"/auth/callback#access_token={quote(access_token)}"
    )
    response.delete_cookie(OAUTH_COOKIE, path="/")
    return response
