"""Login controller tests: the user service is mocked."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from app.api.messages import MESSAGES
from app.domain.errors import ErrorCode, InactiveUser, InvalidCredentials
from app.domain.models import User
from tests.fakes import make_user

API = "/api/v1"


def detail(code: ErrorCode) -> str:
    return MESSAGES[code].message


def test_access_token_returns_a_token(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
) -> None:
    as_anonymous()
    user = make_user(email="person@example.com")
    captured: dict[str, Any] = {}

    def fake_auth(*, conn: Any, email: str, password: str) -> User:
        captured["email"] = email
        captured["password"] = password
        return user

    monkeypatch.setattr("app.services.users.authenticate", fake_auth)

    response = client.post(
        f"{API}/login/access-token",
        data={"username": "person@example.com", "password": "password123"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]
    assert captured == {"email": "person@example.com", "password": "password123"}


def test_bad_credentials_are_400(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
) -> None:
    as_anonymous()

    def fake_auth(*, conn: Any, email: str, password: str) -> User:
        raise InvalidCredentials(ErrorCode.INVALID_CREDENTIALS)

    monkeypatch.setattr("app.services.users.authenticate", fake_auth)

    response = client.post(
        f"{API}/login/access-token",
        data={"username": "person@example.com", "password": "wrong"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == detail(ErrorCode.INVALID_CREDENTIALS)


def test_inactive_user_is_400(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
) -> None:
    as_anonymous()

    def fake_auth(*, conn: Any, email: str, password: str) -> User:
        raise InactiveUser(ErrorCode.INACTIVE_USER)

    monkeypatch.setattr("app.services.users.authenticate", fake_auth)

    response = client.post(
        f"{API}/login/access-token",
        data={"username": "person@example.com", "password": "password123"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == detail(ErrorCode.INACTIVE_USER)


def test_test_token_returns_the_actor(
    client: TestClient, as_user: Callable[[User], None]
) -> None:
    as_user(make_user(email="me@example.com"))

    response = client.post(f"{API}/login/test-token")

    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"
