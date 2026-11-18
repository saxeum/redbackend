"""Repository tests against a real PostgreSQL (persistence is not mocked)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.db import DBConnection
from app.domain.errors import Conflict, ErrorCode
from app.domain.models import User
from app.repositories import users as user_repo
from tests.utils.utils import random_email


def _user(*, email: str | None = None, created_at: datetime | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        email=email or random_email(),
        full_name=None,
        is_active=True,
        is_superuser=False,
        hashed_password="hash",
        created_at=created_at or datetime.now(UTC),
    )


def test_insert_then_read_back(db: DBConnection) -> None:
    user = _user()

    stored = user_repo.insert(conn=db, user=user)

    assert stored == user
    assert user_repo.get_by_id(conn=db, user_id=user.id) == user
    assert user_repo.get_by_email(conn=db, email=user.email) == user


def test_insert_translates_unique_violation(db: DBConnection) -> None:
    user = _user()
    user_repo.insert(conn=db, user=user)

    with pytest.raises(Conflict) as exc:
        user_repo.insert(conn=db, user=_user(email=user.email))

    assert exc.value.code is ErrorCode.EMAIL_TAKEN_ON_CREATE


def test_update_only_touches_supplied_columns(db: DBConnection) -> None:
    user = _user()
    user_repo.insert(conn=db, user=user)

    updated = user_repo.update(
        conn=db, user_id=user.id, changes={"full_name": "Renamed"}
    )

    assert updated is not None
    assert updated.full_name == "Renamed"
    assert updated.email == user.email
    assert updated.hashed_password == user.hashed_password


def test_update_missing_row_returns_none(db: DBConnection) -> None:
    assert (
        user_repo.update(conn=db, user_id=uuid.uuid4(), changes={"full_name": "X"})
        is None
    )


def test_list_page_orders_by_created_at_desc(db: DBConnection) -> None:
    older = _user(created_at=datetime.now(UTC) - timedelta(days=1))
    newer = _user(created_at=datetime.now(UTC))
    user_repo.insert(conn=db, user=older)
    user_repo.insert(conn=db, user=newer)

    page, count = user_repo.list_page(conn=db, skip=0, limit=100)

    assert count >= 2
    assert page.index(newer) < page.index(older)


def test_delete_reports_whether_a_row_existed(db: DBConnection) -> None:
    user = _user()
    user_repo.insert(conn=db, user=user)

    assert user_repo.delete(conn=db, user_id=user.id) is True
    assert user_repo.delete(conn=db, user_id=user.id) is False
