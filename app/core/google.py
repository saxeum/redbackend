"""Verify Google OpenID Connect ID tokens.

Uses the public JWKS (no client secret): the token's audience must be our OAuth
client id, the issuer must be Google's, and the email must be verified.

The OAuth client is the same one zuchat uses; only its client id is needed here.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from app.core.config import settings
from app.domain.errors import AuthenticationFailed, ErrorCode

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


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
