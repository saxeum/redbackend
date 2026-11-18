from collections.abc import Generator
from typing import Any, cast

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app.core.config import settings
from app.core.db import DBConnection
from app.main import app
from app.repositories import users as user_repo
from app.services import users as user_service
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import TEST_USER_EMAIL, get_superuser_token_headers


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[DBConnection]:
    # A dedicated autocommit connection: rows written through crud are visible
    # immediately to the application's connection pool.
    # psycopg's connect() overload types row_factory for the default tuple rows;
    # passing it through **kwargs keeps the runtime behaviour and the DictRow type.
    conn_options: dict[str, Any] = {"row_factory": dict_row}
    conn = cast(
        DBConnection,
        psycopg.connect(str(settings.DATABASE_URL), autocommit=True, **conn_options),
    )
    try:
        if not user_repo.get_by_email(conn=conn, email=settings.FIRST_SUPERUSER):
            user_service.ensure_superuser(
                conn=conn,
                email=str(settings.FIRST_SUPERUSER),
                password=settings.FIRST_SUPERUSER_PASSWORD,
            )
        yield conn
        conn.execute("DELETE FROM item")
        conn.execute('DELETE FROM "user"')
    finally:
        conn.close()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: DBConnection) -> dict[str, str]:
    return authentication_token_from_email(client=client, email=TEST_USER_EMAIL, db=db)
