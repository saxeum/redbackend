import uuid

import pytest
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.db import DBConnection
from app.core.security import verify_password
from app.domain.commands import CreateUser, UpdateUser
from app.domain.errors import (
    Conflict,
    EmailAlreadyRegistered,
    InactiveUser,
    InvalidCredentials,
    InvalidOperation,
    NotFound,
    PermissionDenied,
)
from app.domain.models import User
from app.repositories import users as user_repo
from app.services import users as user_service
from tests.utils.user import create_test_user, create_user_with_hashed_password
from tests.utils.utils import random_email, random_lower_string


def _actor(db: DBConnection, *, is_superuser: bool = True) -> User:
    return create_test_user(
        db,
        email=random_email(),
        password=random_lower_string(),
        is_superuser=is_superuser,
    )


def test_create_user_by_admin(db: DBConnection) -> None:
    actor = _actor(db)
    email = random_email()

    user = user_service.create_user(
        conn=db, cmd=CreateUser(email=email, password="password123"), actor=actor
    )

    assert user.email == email
    assert user.is_active is True
    assert user.is_superuser is False
    assert user.hashed_password


def test_create_user_requires_superuser(db: DBConnection) -> None:
    actor = _actor(db, is_superuser=False)

    with pytest.raises(PermissionDenied):
        user_service.create_user(
            conn=db,
            cmd=CreateUser(email=random_email(), password="password123"),
            actor=actor,
        )


def test_create_user_duplicate_email(db: DBConnection) -> None:
    actor = _actor(db)
    email = random_email()
    user_service.create_user(
        conn=db, cmd=CreateUser(email=email, password="password123"), actor=actor
    )

    with pytest.raises(EmailAlreadyRegistered):
        user_service.create_user(
            conn=db, cmd=CreateUser(email=email, password="password123"), actor=actor
        )


def test_signup_never_grants_superuser(db: DBConnection) -> None:
    email = random_email()

    user = user_service.signup(
        conn=db,
        cmd=CreateUser(email=email, password="password123", is_superuser=True),
    )

    assert user.is_superuser is False
    assert user_repo.get_by_email(conn=db, email=email) is not None


def test_authenticate_user(db: DBConnection) -> None:
    email = random_email()
    password = random_lower_string()
    user_service.signup(conn=db, cmd=CreateUser(email=email, password=password))

    authenticated = user_service.authenticate(conn=db, email=email, password=password)

    assert authenticated.email == email


def test_authenticate_unknown_email(db: DBConnection) -> None:
    with pytest.raises(InvalidCredentials):
        user_service.authenticate(
            conn=db, email=random_email(), password=random_lower_string()
        )


def test_authenticate_wrong_password(db: DBConnection) -> None:
    email = random_email()
    user_service.signup(
        conn=db, cmd=CreateUser(email=email, password=random_lower_string())
    )

    with pytest.raises(InvalidCredentials):
        user_service.authenticate(conn=db, email=email, password=random_lower_string())


def test_authenticate_inactive_user(db: DBConnection) -> None:
    email = random_email()
    password = random_lower_string()
    create_test_user(db, email=email, password=password, is_active=False)

    with pytest.raises(InactiveUser):
        user_service.authenticate(conn=db, email=email, password=password)


def test_authenticate_upgrades_bcrypt_hash(db: DBConnection) -> None:
    email = random_email()
    password = random_lower_string()
    bcrypt_hash = BcryptHasher().hash(password)
    create_user_with_hashed_password(db=db, email=email, hashed_password=bcrypt_hash)

    authenticated = user_service.authenticate(conn=db, email=email, password=password)

    refreshed = user_repo.get_by_id(conn=db, user_id=authenticated.id)
    assert refreshed
    assert refreshed.hashed_password.startswith("$argon2")


def test_get_user_self(db: DBConnection) -> None:
    user = create_test_user(db, email=random_email(), password=random_lower_string())

    found = user_service.get_user(conn=db, user_id=user.id, actor=user)

    assert found == user


def test_get_user_other_as_normal_user(db: DBConnection) -> None:
    actor = _actor(db, is_superuser=False)
    other = create_test_user(db, email=random_email(), password=random_lower_string())

    with pytest.raises(PermissionDenied):
        user_service.get_user(conn=db, user_id=other.id, actor=actor)


def test_get_missing_user_as_superuser(db: DBConnection) -> None:
    actor = _actor(db)

    with pytest.raises(NotFound):
        user_service.get_user(conn=db, user_id=uuid.uuid4(), actor=actor)


def test_list_users_requires_superuser(db: DBConnection) -> None:
    actor = _actor(db, is_superuser=False)

    with pytest.raises(PermissionDenied):
        user_service.list_users(conn=db, actor=actor, skip=0, limit=10)


def test_update_user_email_conflict(db: DBConnection) -> None:
    actor = _actor(db)
    first = create_test_user(db, email=random_email(), password=random_lower_string())
    second = create_test_user(db, email=random_email(), password=random_lower_string())

    with pytest.raises(Conflict):
        user_service.update_user(
            conn=db,
            user_id=second.id,
            cmd=UpdateUser(email=first.email, fields_set=frozenset({"email"})),
            actor=actor,
        )


def test_update_me_changes_full_name(db: DBConnection) -> None:
    user = create_test_user(db, email=random_email(), password=random_lower_string())

    updated = user_service.update_me(
        conn=db,
        actor=user,
        cmd=UpdateUser(full_name="Jane", fields_set=frozenset({"full_name"})),
    )

    assert updated.full_name == "Jane"


def test_update_me_can_clear_full_name(db: DBConnection) -> None:
    user = create_test_user(db, email=random_email(), password=random_lower_string())
    user_service.update_me(
        conn=db,
        actor=user,
        cmd=UpdateUser(full_name="Jane", fields_set=frozenset({"full_name"})),
    )

    updated = user_service.update_me(
        conn=db,
        actor=user,
        cmd=UpdateUser(full_name=None, fields_set=frozenset({"full_name"})),
    )

    assert updated.full_name is None


def test_change_password_wrong_current(db: DBConnection) -> None:
    user = create_test_user(db, email=random_email(), password=random_lower_string())

    with pytest.raises(InvalidCredentials):
        user_service.change_password(
            conn=db,
            actor=user,
            current_password="wrongpassword1",
            new_password="newpassword1",
        )


def test_change_password_same_value(db: DBConnection) -> None:
    password = random_lower_string()
    user = create_test_user(db, email=random_email(), password=password)

    with pytest.raises(InvalidOperation):
        user_service.change_password(
            conn=db,
            actor=user,
            current_password=password,
            new_password=password,
        )


def test_change_password_updates_hash(db: DBConnection) -> None:
    password = random_lower_string()
    new_password = random_lower_string()
    user = create_test_user(db, email=random_email(), password=password)

    user_service.change_password(
        conn=db, actor=user, current_password=password, new_password=new_password
    )

    refreshed = user_repo.get_by_id(conn=db, user_id=user.id)
    assert refreshed
    verified, _ = verify_password(new_password, refreshed.hashed_password)
    assert verified


def test_delete_me_forbidden_for_superuser(db: DBConnection) -> None:
    actor = _actor(db)

    with pytest.raises(PermissionDenied):
        user_service.delete_me(conn=db, actor=actor)


def test_delete_user_self_forbidden(db: DBConnection) -> None:
    actor = _actor(db)

    with pytest.raises(PermissionDenied):
        user_service.delete_user(conn=db, user_id=actor.id, actor=actor)


def test_delete_missing_user(db: DBConnection) -> None:
    actor = _actor(db)

    with pytest.raises(NotFound):
        user_service.delete_user(conn=db, user_id=uuid.uuid4(), actor=actor)
