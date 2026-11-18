"""Google OpenID Connect: ID-token verification and the authorization-code flow.

The browser never sees the OAuth client secret. The SPA starts the flow at the
backend, Google redirects to the backend callback, and the backend exchanges the
authorization code for tokens.
"""

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib import error, parse
from urllib import request as urlrequest

import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from app.core.config import settings
from app.domain.errors import AuthenticationFailed, ErrorCode

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_SCOPES = "openid email profile"


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    subject: str
    email: str
    email_verified: bool
    name: str | None


@lru_cache
def _jwks() -> PyJWKClient:
    return PyJWKClient(GOOGLE_JWKS_URL)


def is_google_token(token: str) -> bool:
    """Google ID tokens are RS256; our own access tokens are HS256."""
    try:
        header: dict[str, Any] = jwt.get_unverified_header(token)
    except InvalidTokenError:
        return False
    return header.get("alg") == "RS256"


def verify_google_id_token(token: str) -> GoogleIdentity:
    audience = settings.GOOGLE_CLIENT_ID
    if not audience:
        # Not configured: fail closed rather than accepting unverified identities.
        raise AuthenticationFailed(ErrorCode.INVALID_TOKEN)

    try:
        signing_key = _jwks().get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=list(GOOGLE_ISSUERS),
        )
    except InvalidTokenError, PyJWKClientError:
        raise AuthenticationFailed(ErrorCode.INVALID_TOKEN)

    subject = claims.get("sub")
    email = claims.get("email")
    email_verified = claims.get("email_verified") is True
    if not subject or not email or not email_verified:
        raise AuthenticationFailed(ErrorCode.INVALID_TOKEN)

    return GoogleIdentity(
        subject=str(subject),
        email=str(email),
        email_verified=email_verified,
        name=claims.get("name"),
    )


def create_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def authorization_url(*, state: str, code_challenge: str) -> str:
    """Build Google's authorization URL for the redirect flow."""
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID or "",
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{parse.urlencode(params)}"


def exchange_code_for_id_token(*, code: str, code_verifier: str) -> str:
    """Exchange an authorization code for Google tokens and return the ID token."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise AuthenticationFailed(ErrorCode.INVALID_TOKEN)

    body = parse.urlencode(
        {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        }
    ).encode()
    token_request = urlrequest.Request(
        GOOGLE_TOKEN_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urlrequest.urlopen(token_request, timeout=10) as response:
            payload = json.loads(response.read())
    except error.HTTPError, error.URLError, TimeoutError, ValueError:
        raise AuthenticationFailed(ErrorCode.INVALID_TOKEN)

    id_token = payload.get("id_token") if isinstance(payload, dict) else None
    if not id_token:
        raise AuthenticationFailed(ErrorCode.INVALID_TOKEN)
    return str(id_token)
