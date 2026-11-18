from collections.abc import Callable, Generator
from typing import Any, cast

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.db import DBConnection
from app.domain.models import User
from app.main import app


@pytest.fixture(scope="session")
def db() -> Generator[DBConnection]:
    """Real connection for repository tests (persistence is not mocked)."""
    conn_options: dict[str, Any] = {"row_factory": dict_row}
    conn = cast(
        DBConnection,
        psycopg.connect(str(settings.DATABASE_URL), autocommit=True, **conn_options),
    )
    try:
        yield conn
        conn.execute("DELETE FROM item")
        conn.execute("DELETE FROM mail_message")
        conn.execute('DELETE FROM "user"')
    finally:
        conn.close()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_dependency_overrides() -> Generator[None]:
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _deterministic_auth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the suite independent of whatever the local .env happens to say."""
    monkeypatch.setattr(settings, "ALLOWED_EMAILS", "")
    monkeypatch.setattr(settings, "ENABLE_PASSWORD_LOGIN", True)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", None)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", None)


@pytest.fixture
def as_user() -> Callable[[User], None]:
    """Act as an authenticated actor with the service layer mocked out."""

    def _as(user: User) -> None:
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: None

    return _as


@pytest.fixture
def as_anonymous() -> Callable[[], None]:
    """No auth; used by signup and login controllers."""

    def _anonymous() -> None:
        app.dependency_overrides[get_db] = lambda: None

    return _anonymous
