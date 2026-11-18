import uuid

from fastapi.testclient import TestClient

from app import crud
from app.core.config import settings
from app.core.db import DBConnection
from app.models import UserCreate, UserRow, UserUpdate
from tests.utils.utils import random_email, random_lower_string


def user_authentication_headers(
    *, client: TestClient, email: str, password: str
) -> dict[str, str]:
    data = {"username": email, "password": password}

    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=data)
    response = r.json()
    auth_token = response["access_token"]
    headers = {"Authorization": f"Bearer {auth_token}"}
    return headers


def create_random_user(db: DBConnection) -> UserRow:
    email = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=email, password=password)
    return crud.create_user(conn=db, user_create=user_in)


def create_user_with_hashed_password(
    *, db: DBConnection, email: str, hashed_password: str
) -> UserRow:
    """Insert a user row with a pre-computed hash (for legacy-hash tests)."""
    user_id = uuid.uuid4()
    db.execute(
        'INSERT INTO "user" (id, email, is_active, is_superuser, hashed_password)'
        " VALUES (%s, %s, %s, %s, %s)",
        (user_id, email, True, False, hashed_password),
    )
    user = crud.get_user_by_id(conn=db, user_id=user_id)
    assert user
    return user


def authentication_token_from_email(
    *, client: TestClient, email: str, db: DBConnection
) -> dict[str, str]:
    """
    Return a valid token for the user with given email.

    If the user doesn't exist it is created first.
    """
    password = random_lower_string()
    user = crud.get_user_by_email(conn=db, email=email)
    if not user:
        user_in_create = UserCreate(email=email, password=password)
        crud.create_user(conn=db, user_create=user_in_create)
    else:
        crud.update_user(
            conn=db, user_id=user.id, user_in=UserUpdate(password=password)
        )

    return user_authentication_headers(client=client, email=email, password=password)
