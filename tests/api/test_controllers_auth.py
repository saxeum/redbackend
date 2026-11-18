"""Google sign-in controller tests.

The controller owns two adapters: the ID-token verifier (network + parsing) and
the user service. Both are mocked here; their own behaviour is tested in
tests/api/test_deps.py and tests/services/test_users.py.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.messages import MESSAGES
from app.core.google import GoogleIdentity
from app.domain.errors import (
    AuthenticationFailed,
    ErrorCode,
    InactiveUser,
    PermissionDenied,
)
from app.domain.models import User
from tests.fakes import make_user

API = "/api/v1"
IDENTITY = GoogleIdentity(
    subject="google-subject-1",
    email="person@example.com",
    email_verified=True,
    name="Person",
)


def detail(code: ErrorCode) -> str:
    return MESSAGES[code].message


@pytest.fixture
def verified_identity(monkeypatch: Any) -> dict[str, Any]:
    """Replace the verifier and capture what the controller passes on."""
    captured: dict[str, Any] = {}

    def fake_verify(token: str) -> GoogleIdentity:
        captured["token"] = token
        return IDENTITY

    monkeypatch.setattr("app.api.routes.auth.verify_google_id_token", fake_verify)
    return captured


def test_returns_the_local_account(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
    verified_identity: dict[str, Any],
) -> None:
    as_anonymous()
    user = make_user(email="person@example.com", google_sub=IDENTITY.subject)
    captured: dict[str, Any] = {}

    def fake_login(*, conn: Any, identity: GoogleIdentity) -> User:
        captured["identity"] = identity
        return user

    monkeypatch.setattr("app.services.users.login_with_google", fake_login)

    response = client.post(f"{API}/auth/google", json={"id_token": "google-token"})

    assert response.status_code == 200
    assert response.json()["email"] == "person@example.com"
    assert "hashed_password" not in response.json()
    assert verified_identity["token"] == "google-token"
    assert captured["identity"] is IDENTITY


def test_invalid_token_is_401(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
) -> None:
    as_anonymous()

    def fake_verify(token: str) -> GoogleIdentity:
        raise AuthenticationFailed(ErrorCode.INVALID_TOKEN)

    monkeypatch.setattr("app.api.routes.auth.verify_google_id_token", fake_verify)

    response = client.post(f"{API}/auth/google", json={"id_token": "bogus"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"] == detail(ErrorCode.INVALID_TOKEN)


def test_account_outside_the_allowlist_is_403(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
    verified_identity: dict[str, Any],
) -> None:
    as_anonymous()

    def fake_login(*, conn: Any, identity: GoogleIdentity) -> User:
        raise PermissionDenied(ErrorCode.EMAIL_NOT_ALLOWED)

    monkeypatch.setattr("app.services.users.login_with_google", fake_login)

    response = client.post(f"{API}/auth/google", json={"id_token": "google-token"})

    assert response.status_code == 403
    assert response.json()["detail"] == detail(ErrorCode.EMAIL_NOT_ALLOWED)


def test_inactive_account_is_400(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
    verified_identity: dict[str, Any],
) -> None:
    as_anonymous()

    def fake_login(*, conn: Any, identity: GoogleIdentity) -> User:
        raise InactiveUser(ErrorCode.INACTIVE_USER)

    monkeypatch.setattr("app.services.users.login_with_google", fake_login)

    response = client.post(f"{API}/auth/google", json={"id_token": "google-token"})

    assert response.status_code == 400
    assert response.json()["detail"] == detail(ErrorCode.INACTIVE_USER)


def test_missing_id_token_is_rejected(
    client: TestClient, as_anonymous: Callable[[], None]
) -> None:
    as_anonymous()

    assert client.post(f"{API}/auth/google", json={}).status_code == 422
