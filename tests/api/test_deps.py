"""The auth dependency translates tokens into domain errors or an actor."""

import base64
import json
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.api.messages import MESSAGES
from app.core import security
from app.core.config import settings
from app.core.google import GoogleIdentity
from app.domain.errors import (
    AuthenticationFailed,
    ErrorCode,
    InactiveUser,
    NotFound,
)
from app.domain.models import User
from app.main import app
from tests.fakes import CONN, make_user

API = "/api/v1"

IDENTITY = GoogleIdentity(
    subject="google-subject-1",
    email="person@example.com",
    email_verified=True,
    name="Person",
)


def _token(subject: str) -> str:
    return security.create_access_token(subject, expires_delta=timedelta(minutes=5))


def _rs256_token() -> str:
    """A token whose header says RS256, which is enough to route it to Google."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode())
    return header.rstrip(b"=").decode() + ".e30.c2ln"


def test_malformed_token_is_authentication_failed() -> None:
    with pytest.raises(AuthenticationFailed) as exc:
        get_current_user(conn=CONN, token="not-a-jwt")

    assert exc.value.code is ErrorCode.INVALID_TOKEN


def test_non_uuid_subject_is_authentication_failed() -> None:
    with pytest.raises(AuthenticationFailed) as exc:
        get_current_user(conn=CONN, token=_token("not-a-uuid"))

    assert exc.value.code is ErrorCode.INVALID_TOKEN


def test_missing_user_is_authentication_failed(monkeypatch: Any) -> None:
    """A validly signed token for a deleted user is a credential failure."""

    def fake_get_active(*, conn: Any, user_id: Any) -> User:
        raise NotFound(ErrorCode.USER_NOT_FOUND)

    monkeypatch.setattr("app.api.deps.user_service.get_active_user", fake_get_active)

    with pytest.raises(AuthenticationFailed) as exc:
        get_current_user(conn=CONN, token=_token(str(uuid.uuid4())))

    assert exc.value.code is ErrorCode.INVALID_TOKEN


def test_missing_user_token_is_401_over_http(
    client: TestClient, monkeypatch: Any
) -> None:
    """The contract a client sees: 401 with a bearer challenge, not 404."""

    def fake_get_active(*, conn: Any, user_id: Any) -> User:
        raise NotFound(ErrorCode.USER_NOT_FOUND)

    monkeypatch.setattr("app.api.deps.user_service.get_active_user", fake_get_active)
    app.dependency_overrides[get_db] = lambda: None
    token = _token(str(uuid.uuid4()))

    response = client.get(
        f"{API}/users/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["detail"] == MESSAGES[ErrorCode.INVALID_TOKEN].message


def test_valid_token_returns_the_actor(monkeypatch: Any) -> None:
    user = make_user()

    def fake_get_active(*, conn: Any, user_id: Any) -> User:
        return user

    monkeypatch.setattr("app.api.deps.user_service.get_active_user", fake_get_active)

    assert get_current_user(conn=CONN, token=_token(str(user.id))) == user


def test_inactive_actor_propagates(monkeypatch: Any) -> None:
    def fake_get_active(*, conn: Any, user_id: Any) -> User:
        raise InactiveUser(ErrorCode.INACTIVE_USER)

    monkeypatch.setattr("app.api.deps.user_service.get_active_user", fake_get_active)

    with pytest.raises(InactiveUser) as exc:
        get_current_user(conn=CONN, token=_token(str(make_user().id)))

    assert exc.value.code is ErrorCode.INACTIVE_USER


def test_rs256_token_is_routed_to_google(monkeypatch: Any) -> None:
    user = make_user(google_sub=IDENTITY.subject)
    captured: dict[str, Any] = {}

    def fake_verify(token: str) -> GoogleIdentity:
        return IDENTITY

    def fake_login(*, conn: Any, identity: GoogleIdentity) -> User:
        captured["identity"] = identity
        return user

    monkeypatch.setattr("app.api.deps.verify_google_id_token", fake_verify)
    monkeypatch.setattr("app.api.deps.user_service.login_with_google", fake_login)

    assert get_current_user(conn=CONN, token=_rs256_token()) == user
    assert captured["identity"] is IDENTITY


def test_invalid_google_token_is_authentication_failed(monkeypatch: Any) -> None:
    def fake_verify(token: str) -> GoogleIdentity:
        raise AuthenticationFailed(ErrorCode.INVALID_TOKEN)

    monkeypatch.setattr("app.api.deps.verify_google_id_token", fake_verify)

    with pytest.raises(AuthenticationFailed) as exc:
        get_current_user(conn=CONN, token=_rs256_token())

    assert exc.value.code is ErrorCode.INVALID_TOKEN


def test_password_tokens_are_rejected_when_password_login_is_off(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(settings, "ENABLE_PASSWORD_LOGIN", False)

    with pytest.raises(AuthenticationFailed) as exc:
        get_current_user(conn=CONN, token=_token(str(make_user().id)))

    assert exc.value.code is ErrorCode.INVALID_TOKEN
