"""Runtime config endpoint: the SPA decides what to render from this."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import settings

API = "/api/v1"


def test_config_reports_the_defaults(
    client: TestClient, as_anonymous: Callable[[], None]
) -> None:
    as_anonymous()

    response = client.get(f"{API}/utils/config")

    assert response.status_code == 200
    assert response.json() == {
        "password_login": True,
        "google_login": False,
        "google_client_id": None,
    }


def test_config_reflects_the_deployment(
    client: TestClient,
    as_anonymous: Callable[[], None],
    monkeypatch: Any,
) -> None:
    as_anonymous()
    monkeypatch.setattr(settings, "ENABLE_PASSWORD_LOGIN", False)
    monkeypatch.setattr(
        settings, "GOOGLE_CLIENT_ID", "client.apps.googleusercontent.com"
    )
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "secret")

    assert client.get(f"{API}/utils/config").json() == {
        "password_login": False,
        "google_login": True,
        "google_client_id": "client.apps.googleusercontent.com",
    }
