"""User use cases: business rules only, transport-agnostic."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from app.core.db import DBConnection, commit
from app.core.security import get_password_hash, verify_password
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

# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"

INSUFFICIENT_PRIVILEGES = "The user doesn't have enough privileges"


def _require_superuser(actor: User) -> None:
    if not actor.is_superuser:
        raise PermissionDenied(INSUFFICIENT_PRIVILEGES)


def _changes(cmd: UpdateUser) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if "email" in cmd.fields_set and cmd.email is not None:
        changes["email"] = cmd.email
    if "full_name" in cmd.fields_set:
        changes["full_name"] = cmd.full_name
    if "is_active" in cmd.fields_set and cmd.is_active is not None:
        changes["is_active"] = cmd.is_active
    if "is_superuser" in cmd.fields_set and cmd.is_superuser is not None:
        changes["is_superuser"] = cmd.is_superuser
    if "password" in cmd.fields_set and cmd.password is not None:
        changes["hashed_password"] = get_password_hash(cmd.password)
    return changes


def _assert_email_available(
    *, conn: DBConnection, email: str, user_id: uuid.UUID
) -> None:
    existing = user_repo.get_by_email(conn=conn, email=email)
    if existing and existing.id != user_id:
        raise Conflict("User with this email already exists")


def _insert(*, conn: DBConnection, cmd: CreateUser) -> User:
    if user_repo.get_by_email(conn=conn, email=cmd.email):
        raise EmailAlreadyRegistered(
            "The user with this email already exists in the system"
        )
    user = User(
        id=uuid.uuid4(),
        email=cmd.email,
        full_name=cmd.full_name,
        is_active=True,
        is_superuser=cmd.is_superuser,
        hashed_password=get_password_hash(cmd.password),
        created_at=datetime.now(UTC),
    )
    user = user_repo.insert(conn=conn, user=user)
    commit(conn)
    return user


def create_user(*, conn: DBConnection, cmd: CreateUser, actor: User) -> User:
    """Admin-initiated account creation."""
    _require_superuser(actor)
    return _insert(conn=conn, cmd=cmd)


def signup(*, conn: DBConnection, cmd: CreateUser) -> User:
    """Public self-registration: never grants privileges."""
    return _insert(conn=conn, cmd=replace(cmd, is_superuser=False))


def ensure_superuser(*, conn: DBConnection, email: str, password: str) -> None:
    """Bootstrap operation used by the seeding script; idempotent."""
    if user_repo.get_by_email(conn=conn, email=email):
        return
    _insert(
        conn=conn,
        cmd=CreateUser(email=email, password=password, is_superuser=True),
    )


def authenticate(*, conn: DBConnection, email: str, password: str) -> User:
    user = user_repo.get_by_email(conn=conn, email=email)
    if not user:
        # Prove the same amount of work whether or not the email exists.
        verify_password(password, DUMMY_HASH)
        raise InvalidCredentials("Incorrect email or password")
    verified, updated_password_hash = verify_password(password, user.hashed_password)
    if not verified:
        raise InvalidCredentials("Incorrect email or password")
    if not user.is_active:
        raise InactiveUser("Inactive user")
    if updated_password_hash:
        updated = user_repo.update(
            conn=conn,
            user_id=user.id,
            changes={"hashed_password": updated_password_hash},
        )
        commit(conn)
        return updated or user
    return user


def get_active_user(*, conn: DBConnection, user_id: uuid.UUID) -> User:
    """Resolve a token subject to an active user (used by the auth dependency)."""
    user = user_repo.get_by_id(conn=conn, user_id=user_id)
    if not user:
        raise NotFound("User not found")
    if not user.is_active:
        raise InactiveUser("Inactive user")
    return user


def get_user(*, conn: DBConnection, user_id: uuid.UUID, actor: User) -> User:
    user = user_repo.get_by_id(conn=conn, user_id=user_id)
    if user and user.id == actor.id:
        return user
    if not actor.is_superuser:
        raise PermissionDenied(INSUFFICIENT_PRIVILEGES)
    if user is None:
        raise NotFound("User not found")
    return user


def list_users(
    *, conn: DBConnection, actor: User, skip: int, limit: int
) -> tuple[list[User], int]:
    _require_superuser(actor)
    return user_repo.list_page(conn=conn, skip=skip, limit=limit)


def update_user(
    *, conn: DBConnection, user_id: uuid.UUID, cmd: UpdateUser, actor: User
) -> User:
    _require_superuser(actor)
    if not user_repo.get_by_id(conn=conn, user_id=user_id):
        raise NotFound("The user with this id does not exist in the system")
    if "email" in cmd.fields_set and cmd.email is not None:
        _assert_email_available(conn=conn, email=cmd.email, user_id=user_id)
    updated = user_repo.update(conn=conn, user_id=user_id, changes=_changes(cmd))
    if updated is None:
        raise NotFound("The user with this id does not exist in the system")
    commit(conn)
    return updated


def update_me(*, conn: DBConnection, actor: User, cmd: UpdateUser) -> User:
    if "email" in cmd.fields_set and cmd.email is not None:
        _assert_email_available(conn=conn, email=cmd.email, user_id=actor.id)
    updated = user_repo.update(conn=conn, user_id=actor.id, changes=_changes(cmd))
    if updated is None:
        raise NotFound("User not found")
    commit(conn)
    return updated


def change_password(
    *, conn: DBConnection, actor: User, current_password: str, new_password: str
) -> None:
    verified, _ = verify_password(current_password, actor.hashed_password)
    if not verified:
        raise InvalidCredentials("Incorrect password")
    if current_password == new_password:
        raise InvalidOperation("New password cannot be the same as the current one")
    updated = user_repo.update(
        conn=conn,
        user_id=actor.id,
        changes={"hashed_password": get_password_hash(new_password)},
    )
    if updated is None:
        raise NotFound("User not found")
    commit(conn)


def delete_user(*, conn: DBConnection, user_id: uuid.UUID, actor: User) -> None:
    _require_superuser(actor)
    user = user_repo.get_by_id(conn=conn, user_id=user_id)
    if not user:
        raise NotFound("User not found")
    if user.id == actor.id:
        raise PermissionDenied("Super users are not allowed to delete themselves")
    user_repo.delete(conn=conn, user_id=user_id)
    commit(conn)


def delete_me(*, conn: DBConnection, actor: User) -> None:
    if actor.is_superuser:
        raise PermissionDenied("Super users are not allowed to delete themselves")
    user_repo.delete(conn=conn, user_id=actor.id)
    commit(conn)
