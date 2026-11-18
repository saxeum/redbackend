"""The auth dependency translates tokens into domain errors or an actor."""

from datetime import timedelta
from typing import Any

import pytest

from app.api.deps import get_current_user
from app.core import security
from app.domain.errors import (
    AuthenticationFailed,
    ErrorCode,
    InactiveUser,
    NotFound,
)
from app.domain.models import User
from tests.fakes import CONN, make_user


def _token(subject: str) -> str:
    return security.create_access_token(subject, expires_delta=timedelta(minutes=5))


def test_malformed_token_is_authentication_failed() -> None:
    with pytest.raises(AuthenticationFailed) as exc:
        get_current_user(conn=CONN, token="not-a-jwt")

    assert exc.value.code is ErrorCode.INVALID_TOKEN


def test_non_uuid_subject_is_not_found() -> None:
    with pytest.raises(NotFound) as exc:
        get_current_user(conn=CONN, token=_token("not-a-uuid"))

    assert exc.value.code is ErrorCode.USER_NOT_FOUND


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
