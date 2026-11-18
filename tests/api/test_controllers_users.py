"""Controller tests: the service layer is mocked; HTTP concerns are real."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.messages import MESSAGES
from app.domain.commands import UpdateUser
from app.domain.errors import (
    Conflict,
    DomainError,
    ErrorCode,
    InvalidCredentials,
    InvalidOperation,
    NotFound,
    PermissionDenied,
)
from app.domain.models import User
from tests.fakes import make_user

API = "/api/v1"


def detail(code: ErrorCode) -> str:
    return MESSAGES[code].message


def test_read_me_maps_the_actor(
    client: TestClient, as_user: Callable[[User], None]
) -> None:
    user = make_user(email="me@example.com", full_name="Me")
    as_user(user)

    response = client.get(f"{API}/users/me")

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "me@example.com"
    assert body["full_name"] == "Me"
    assert body["has_password"] is True
    assert "hashed_password" not in body


def test_read_me_reports_a_google_only_account(
    client: TestClient, as_user: Callable[[User], None]
) -> None:
    as_user(make_user(email="google@example.com", hashed_password=None))

    assert client.get(f"{API}/users/me").json()["has_password"] is False


def test_list_users_returns_page(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user(is_superuser=True))
    users = [make_user(email="a@example.com"), make_user(email="b@example.com")]
    monkeypatch.setattr(
        "app.services.users.list_users",
        lambda *, conn, actor, skip, limit: (users, 2),
    )

    response = client.get(f"{API}/users/")

    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert [u["email"] for u in response.json()["data"]] == [
        "a@example.com",
        "b@example.com",
    ]


def test_create_user_maps_request_to_command(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user(is_superuser=True))
    captured: dict[str, Any] = {}
    created = make_user(email="made@example.com", full_name="Made")

    def fake_create(*, conn: Any, cmd: Any, actor: User) -> User:
        captured["cmd"] = cmd
        captured["actor"] = actor
        return created

    monkeypatch.setattr("app.services.users.create_user", fake_create)

    response = client.post(
        f"{API}/users/",
        json={
            "email": "made@example.com",
            "password": "password123",
            "full_name": "Made",
            "is_superuser": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["email"] == "made@example.com"
    cmd = captured["cmd"]
    assert cmd.email == "made@example.com"
    assert cmd.full_name == "Made"
    assert cmd.is_superuser is False


def test_create_user_conflict_is_a_bad_request(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user(is_superuser=True))

    def fake_create(*, conn: Any, cmd: Any, actor: User) -> User:
        raise Conflict(ErrorCode.EMAIL_TAKEN_ON_CREATE)

    monkeypatch.setattr("app.services.users.create_user", fake_create)

    response = client.post(
        f"{API}/users/", json={"email": "x@example.com", "password": "password123"}
    )

    assert response.status_code == 400
    assert response.json() == {"detail": detail(ErrorCode.EMAIL_TAKEN_ON_CREATE)}


def test_update_me_passes_only_supplied_fields(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    user = make_user()
    as_user(user)
    captured: dict[str, Any] = {}

    def fake_update_me(*, conn: Any, actor: User, cmd: UpdateUser) -> User:
        captured["cmd"] = cmd
        return make_user(email=user.email, full_name=cmd.full_name)

    monkeypatch.setattr("app.services.users.update_me", fake_update_me)

    response = client.patch(f"{API}/users/me", json={"full_name": "Renamed"})

    assert response.status_code == 200
    assert response.json()["full_name"] == "Renamed"
    assert captured["cmd"].fields_set == frozenset({"full_name"})


def test_update_me_email_conflict_is_409(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user())

    def fake_update_me(*, conn: Any, actor: User, cmd: UpdateUser) -> User:
        raise Conflict(ErrorCode.EMAIL_TAKEN)

    monkeypatch.setattr("app.services.users.update_me", fake_update_me)

    response = client.patch(f"{API}/users/me", json={"email": "taken@example.com"})

    assert response.status_code == 409
    assert response.json() == {"detail": detail(ErrorCode.EMAIL_TAKEN)}


def test_change_password_returns_message(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user())
    captured: dict[str, Any] = {}

    def fake_change(
        *, conn: Any, actor: User, current_password: str, new_password: str
    ) -> None:
        captured["current"] = current_password
        captured["new"] = new_password

    monkeypatch.setattr("app.services.users.change_password", fake_change)

    response = client.patch(
        f"{API}/users/me/password",
        json={"current_password": "password123", "new_password": "newpassword123"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Password updated successfully"}
    assert captured == {"current": "password123", "new": "newpassword123"}


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (InvalidCredentials(ErrorCode.INCORRECT_PASSWORD), 400),
        (InvalidOperation(ErrorCode.PASSWORD_UNCHANGED), 400),
    ],
)
def test_change_password_errors(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
    error: DomainError,
    status_code: int,
) -> None:
    as_user(make_user())

    def fake_change(**_: Any) -> None:
        raise error

    monkeypatch.setattr("app.services.users.change_password", fake_change)

    response = client.patch(
        f"{API}/users/me/password",
        json={"current_password": "password123", "new_password": "newpassword123"},
    )

    assert response.status_code == status_code
    assert response.json()["detail"] == detail(error.code)


def test_delete_me_returns_message(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    user = make_user()
    as_user(user)
    captured: dict[str, Any] = {}

    def fake_delete(*, conn: Any, actor: User) -> None:
        captured["actor"] = actor

    monkeypatch.setattr("app.services.users.delete_me", fake_delete)

    response = client.delete(f"{API}/users/me")

    assert response.status_code == 200
    assert response.json() == {"message": "User deleted successfully"}
    assert captured["actor"] == user


def test_signup_maps_request_without_privileges(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
) -> None:
    as_anonymous()
    captured: dict[str, Any] = {}

    def fake_signup(*, conn: Any, cmd: Any) -> User:
        captured["cmd"] = cmd
        return make_user(email=cmd.email, full_name=cmd.full_name)

    monkeypatch.setattr("app.services.users.signup", fake_signup)

    response = client.post(
        f"{API}/users/signup",
        json={"email": "new@example.com", "password": "password123"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "new@example.com"
    assert captured["cmd"].is_superuser is False


def test_signup_conflict_is_a_bad_request(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
) -> None:
    as_anonymous()

    def fake_signup(*, conn: Any, cmd: Any) -> User:
        raise Conflict(ErrorCode.EMAIL_TAKEN_ON_CREATE)

    monkeypatch.setattr("app.services.users.signup", fake_signup)

    response = client.post(
        f"{API}/users/signup",
        json={"email": "new@example.com", "password": "password123"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == detail(ErrorCode.EMAIL_TAKEN_ON_CREATE)


def test_signup_is_404_when_the_password_grant_is_disabled(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
) -> None:
    as_anonymous()

    def fake_signup(*, conn: Any, cmd: Any) -> User:
        raise InvalidOperation(ErrorCode.PASSWORD_LOGIN_DISABLED)

    monkeypatch.setattr("app.services.users.signup", fake_signup)

    response = client.post(
        f"{API}/users/signup",
        json={"email": "new@example.com", "password": "password123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == detail(ErrorCode.PASSWORD_LOGIN_DISABLED)


def test_read_user_by_id(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user(is_superuser=True))
    target = make_user(email="target@example.com")
    monkeypatch.setattr(
        "app.services.users.get_user",
        lambda *, conn, user_id, actor: target,
    )

    response = client.get(f"{API}/users/{target.id}")

    assert response.status_code == 200
    assert response.json()["email"] == "target@example.com"


def test_read_missing_user_is_404(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user(is_superuser=True))

    def fake_get(*, conn: Any, user_id: Any, actor: User) -> User:
        raise NotFound(ErrorCode.USER_NOT_FOUND)

    monkeypatch.setattr("app.services.users.get_user", fake_get)

    response = client.get(f"{API}/users/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == detail(ErrorCode.USER_NOT_FOUND)


def test_permission_denied_is_403(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user(is_superuser=False))

    def fake_list(*, conn: Any, actor: User, skip: int, limit: int) -> Any:
        raise PermissionDenied(ErrorCode.INSUFFICIENT_PRIVILEGES)

    monkeypatch.setattr("app.services.users.list_users", fake_list)

    response = client.get(f"{API}/users/")

    assert response.status_code == 403
    assert response.json()["detail"] == detail(ErrorCode.INSUFFICIENT_PRIVILEGES)


def test_update_user_not_found(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user(is_superuser=True))

    def fake_update(*, conn: Any, user_id: Any, cmd: Any, actor: User) -> User:
        raise NotFound(ErrorCode.USER_NOT_FOUND_FOR_UPDATE)

    monkeypatch.setattr("app.services.users.update_user", fake_update)

    response = client.patch(f"{API}/users/{uuid.uuid4()}", json={"full_name": "X"})

    assert response.status_code == 404
    assert response.json()["detail"] == detail(ErrorCode.USER_NOT_FOUND_FOR_UPDATE)


def test_delete_user_self_forbidden(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    admin = make_user(is_superuser=True)
    as_user(admin)

    def fake_delete(*, conn: Any, user_id: Any, actor: User) -> None:
        raise PermissionDenied(ErrorCode.SELF_DELETE_FORBIDDEN)

    monkeypatch.setattr("app.services.users.delete_user", fake_delete)

    response = client.delete(f"{API}/users/{admin.id}")

    assert response.status_code == 403
    assert response.json()["detail"] == detail(ErrorCode.SELF_DELETE_FORBIDDEN)
