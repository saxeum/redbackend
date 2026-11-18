"""Google ID-token verification.

No network: the signing key is generated locally and the JWKS client is
replaced with one that returns the matching public key.
"""

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from jwt.exceptions import PyJWKClientError

from app.core import google
from app.core.config import settings
from app.domain.errors import AuthenticationFailed, ErrorCode

CLIENT_ID = "test-client.apps.googleusercontent.com"
ISSUER = "https://accounts.google.com"


@pytest.fixture(scope="module")
def key_pair() -> tuple[RSAPrivateKey, RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


class _SigningKey:
    def __init__(self, key: RSAPublicKey) -> None:
        self.key = key


class _JWKS:
    def __init__(self, key: RSAPublicKey | None = None) -> None:
        self._key = key

    def get_signing_key_from_jwt(self, token: str) -> _SigningKey:
        if self._key is None:
            raise PyJWKClientError("no matching key")
        return _SigningKey(self._key)


@pytest.fixture
def google_configured(monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", CLIENT_ID)


@pytest.fixture
def jwks(monkeypatch: Any, key_pair: tuple[RSAPrivateKey, RSAPublicKey]) -> None:
    public_key = key_pair[1]
    monkeypatch.setattr(google, "_jwks", lambda: _JWKS(public_key))


def _token(
    private_key: RSAPrivateKey,
    *,
    audience: str = CLIENT_ID,
    issuer: str = ISSUER,
    lifetime: int = 300,
    email: str | None = "person@example.com",
    email_verified: bool = True,
    subject: str | None = "google-subject-1",
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + timedelta(seconds=lifetime),
    }
    if subject is not None:
        claims["sub"] = subject
    if email is not None:
        claims["email"] = email
    claims["email_verified"] = email_verified
    claims["name"] = "Person"
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test"})


def test_valid_token_yields_an_identity(
    google_configured: None,
    jwks: None,
    key_pair: tuple[RSAPrivateKey, RSAPublicKey],
) -> None:
    identity = google.verify_google_id_token(_token(key_pair[0]))

    assert identity.subject == "google-subject-1"
    assert identity.email == "person@example.com"
    assert identity.email_verified is True
    assert identity.name == "Person"


def test_unconfigured_client_id_fails_closed(
    key_pair: tuple[RSAPrivateKey, RSAPublicKey],
) -> None:
    with pytest.raises(AuthenticationFailed) as exc:
        google.verify_google_id_token(_token(key_pair[0]))

    assert exc.value.code is ErrorCode.INVALID_TOKEN


def test_wrong_audience_is_rejected(
    google_configured: None,
    jwks: None,
    key_pair: tuple[RSAPrivateKey, RSAPublicKey],
) -> None:
    token = _token(key_pair[0], audience="someone-else.apps.googleusercontent.com")

    with pytest.raises(AuthenticationFailed) as exc:
        google.verify_google_id_token(token)

    assert exc.value.code is ErrorCode.INVALID_TOKEN


def test_wrong_issuer_is_rejected(
    google_configured: None,
    jwks: None,
    key_pair: tuple[RSAPrivateKey, RSAPublicKey],
) -> None:
    token = _token(key_pair[0], issuer="https://evil.example.com")

    with pytest.raises(AuthenticationFailed) as exc:
        google.verify_google_id_token(token)

    assert exc.value.code is ErrorCode.INVALID_TOKEN


def test_expired_token_is_rejected(
    google_configured: None,
    jwks: None,
    key_pair: tuple[RSAPrivateKey, RSAPublicKey],
) -> None:
    token = _token(key_pair[0], lifetime=-60)

    with pytest.raises(AuthenticationFailed) as exc:
        google.verify_google_id_token(token)

    assert exc.value.code is ErrorCode.INVALID_TOKEN


def test_unverified_email_is_rejected(
    google_configured: None,
    jwks: None,
    key_pair: tuple[RSAPrivateKey, RSAPublicKey],
) -> None:
    token = _token(key_pair[0], email_verified=False)

    with pytest.raises(AuthenticationFailed) as exc:
        google.verify_google_id_token(token)

    assert exc.value.code is ErrorCode.INVALID_TOKEN


@pytest.mark.parametrize("missing", ["email", "subject"])
def test_missing_claims_are_rejected(
    google_configured: None,
    jwks: None,
    key_pair: tuple[RSAPrivateKey, RSAPublicKey],
    missing: str,
) -> None:
    token = (
        _token(key_pair[0], email=None)
        if missing == "email"
        else _token(key_pair[0], subject=None)
    )

    with pytest.raises(AuthenticationFailed) as exc:
        google.verify_google_id_token(token)

    assert exc.value.code is ErrorCode.INVALID_TOKEN


def test_unknown_signing_key_is_rejected(
    google_configured: None, monkeypatch: Any
) -> None:
    monkeypatch.setattr(google, "_jwks", lambda: _JWKS(None))

    with pytest.raises(AuthenticationFailed) as exc:
        google.verify_google_id_token("not-a-jwt")

    assert exc.value.code is ErrorCode.INVALID_TOKEN


def test_google_tokens_are_recognised_by_algorithm(
    key_pair: tuple[RSAPrivateKey, RSAPublicKey],
) -> None:
    assert google.is_google_token(_token(key_pair[0])) is True


def test_non_google_tokens_are_not_recognised() -> None:
    assert google.is_google_token("not-a-jwt") is False


def test_hs256_tokens_are_not_recognised() -> None:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode())
    token = header.decode().rstrip("=") + ".e30.c2ln"

    assert google.is_google_token(token) is False
