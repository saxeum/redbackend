"""Google sign-in controller tests.

The controller owns two adapters: the ID-token verifier (network + parsing) and
the user service. Both are mocked here; their own behaviour is tested in
tests/api/test_deps.py and tests/services/test_users.py.
"""

from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.messages import MESSAGES
from app.core import security
from app.core.config import settings
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


def _configure_google(monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setattr(settings, "GOOGLE_REDIRECT_URI", "http://localhost:8000/auth")


def _start_google(client: TestClient) -> str:
    client.cookies.clear()
    response = client.get(f"{API}/auth/google/start", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    return parse_qs(urlparse(location).query)["state"][0]


def test_google_start_redirects_with_state_and_pkce(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
) -> None:
    as_anonymous()
    _configure_google(monkeypatch)
    state = _start_google(client)

    location = client.get(f"{API}/auth/google/start", follow_redirects=False).headers[
        "location"
    ]
    query = parse_qs(urlparse(location).query)
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert query["client_id"] == ["client"]
    assert query["redirect_uri"] == ["http://localhost:8000/auth"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"]
    assert query["state"]
    assert state
    assert "google_oauth" in client.cookies
    client.cookies.clear()


def test_google_start_is_404_when_not_configured(
    client: TestClient,
    as_anonymous: Callable[[], None],
) -> None:
    as_anonymous()

    response = client.get(f"{API}/auth/google/start", follow_redirects=False)

    assert response.status_code == 404
    assert response.json()["detail"] == detail(ErrorCode.GOOGLE_LOGIN_DISABLED)


def test_google_callback_requires_the_state_cookie(
    client: TestClient,
    as_anonymous: Callable[[], None],
) -> None:
    as_anonymous()
    client.cookies.clear()

    response = client.get("/auth?code=auth-code&state=state", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == (
        f"{settings.FRONTEND_HOST}/login?google_error=failed"
    )


def test_google_callback_rejects_state_mismatch(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
) -> None:
    as_anonymous()
    _configure_google(monkeypatch)
    _start_google(client)

    response = client.get("/auth?code=auth-code&state=wrong", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == (
        f"{settings.FRONTEND_HOST}/login?google_error=failed"
    )
    assert "google_oauth" not in client.cookies
    client.cookies.clear()


def test_google_callback_exchanges_code_and_issues_a_token(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
) -> None:
    as_anonymous()
    _configure_google(monkeypatch)
    state = _start_google(client)
    user = make_user(email="person@example.com", google_sub=IDENTITY.subject)
    captured: dict[str, Any] = {}

    def fake_exchange(*, code: str, code_verifier: str) -> str:
        captured["code"] = code
        captured["verifier"] = code_verifier
        return "google-id-token"

    monkeypatch.setattr("app.api.routes.auth.exchange_code_for_id_token", fake_exchange)
    monkeypatch.setattr(
        "app.api.routes.auth.verify_google_id_token", lambda token: IDENTITY
    )
    monkeypatch.setattr(
        "app.api.routes.auth.user_service.login_with_google",
        lambda *, conn, identity: user,
    )

    response = client.get(f"/auth?code=auth-code&state={state}", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    prefix = f"{settings.FRONTEND_HOST.rstrip('/')}/auth/callback#access_token="
    assert location.startswith(prefix)
    token = location.removeprefix(prefix)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
    assert payload["sub"] == str(user.id)
    assert captured["code"] == "auth-code"
    assert captured["verifier"]
    assert "google_oauth" not in client.cookies
    client.cookies.clear()


def test_google_callback_maps_allowlist_errors(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
) -> None:
    as_anonymous()
    _configure_google(monkeypatch)
    state = _start_google(client)

    monkeypatch.setattr(
        "app.api.routes.auth.exchange_code_for_id_token",
        lambda *, code, code_verifier: "google-id-token",
    )
    monkeypatch.setattr(
        "app.api.routes.auth.verify_google_id_token", lambda token: IDENTITY
    )

    def deny(*, conn: Any, identity: GoogleIdentity) -> User:
        raise PermissionDenied(ErrorCode.EMAIL_NOT_ALLOWED)

    monkeypatch.setattr("app.api.routes.auth.user_service.login_with_google", deny)

    response = client.get(f"/auth?code=auth-code&state={state}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == (
        f"{settings.FRONTEND_HOST}/login?google_error=not_allowed"
    )
    client.cookies.clear()
