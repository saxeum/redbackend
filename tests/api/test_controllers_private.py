"""Private (development-only) controller: service mocked."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.domain.models import User
from tests.fakes import make_user

pytestmark = pytest.mark.skipif(
    not settings.ENABLE_PRIVATE_ROUTER, reason="private router is disabled"
)


def test_private_create_user_maps_request(
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
        "/api/v1/private/users/",
        json={
            "email": "private@example.com",
            "password": "password123",
            "full_name": "Private",
        },
    )

    assert response.status_code == 200
    assert response.json()["email"] == "private@example.com"
    assert captured["cmd"].email == "private@example.com"
    assert captured["cmd"].full_name == "Private"
    assert captured["cmd"].is_superuser is False
