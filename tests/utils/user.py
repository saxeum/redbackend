import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.db import DBConnection
from app.core.security import get_password_hash
from app.domain.commands import CreateUser, UpdateUser
from app.domain.models import User
from app.repositories import users as user_repo
from app.services import users as user_service
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


def create_test_user(
    db: DBConnection,
    *,
    email: str,
    password: str,
    is_superuser: bool = False,
    is_active: bool = True,
) -> User:
    """Insert a user row directly, bypassing service rules (test fixtures)."""
    user = User(
        id=uuid.uuid4(),
        email=email,
        full_name=None,
        is_active=is_active,
        is_superuser=is_superuser,
        hashed_password=get_password_hash(password),
        created_at=datetime.now(UTC),
    )
    return user_repo.insert(conn=db, user=user)


def create_random_user(db: DBConnection) -> User:
    return user_service.signup(
        conn=db,
        cmd=CreateUser(email=random_email(), password=random_lower_string()),
    )


def create_user_with_hashed_password(
    *, db: DBConnection, email: str, hashed_password: str
) -> User:
    """Insert a user row with a pre-computed hash (for legacy-hash tests)."""
    user_id = uuid.uuid4()
    db.execute(
        'INSERT INTO "user" (id, email, is_active, is_superuser, hashed_password)'
        " VALUES (%s, %s, %s, %s, %s)",
        (user_id, email, True, False, hashed_password),
    )
    user = user_repo.get_by_id(conn=db, user_id=user_id)
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
    user = user_repo.get_by_email(conn=db, email=email)
    if not user:
        user_service.signup(conn=db, cmd=CreateUser(email=email, password=password))
    else:
        user_service.update_me(
            conn=db,
            actor=user,
            cmd=UpdateUser(password=password, fields_set=frozenset({"password"})),
        )

    return user_authentication_headers(client=client, email=email, password=password)
