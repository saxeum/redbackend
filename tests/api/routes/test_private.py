import uuid

from fastapi.testclient import TestClient

from app import crud
from app.core.config import settings
from app.core.db import DBConnection


def test_create_user(client: TestClient, db: DBConnection) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/private/users/",
        json={
            "email": "user@example.com",
            "password": "password123",
            "full_name": "Pollo Listo",
        },
    )

    assert r.status_code == 200

    data = r.json()

    user = crud.get_user_by_id(conn=db, user_id=uuid.UUID(data["id"]))

    assert user
    assert user.email == "user@example.com"
    assert user.full_name == "Pollo Listo"
