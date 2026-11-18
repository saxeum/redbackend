"""Item repository tests against a real PostgreSQL."""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.db import DBConnection
from app.domain.models import Item, User
from app.repositories import items as item_repo
from app.repositories import users as user_repo
from tests.utils.utils import random_email


def _owner(db: DBConnection) -> User:
    user = User(
        id=uuid.uuid4(),
        email=random_email(),
        full_name=None,
        is_active=True,
        is_superuser=False,
        hashed_password="hash",
        created_at=datetime.now(UTC),
    )
    return user_repo.insert(conn=db, user=user)


def _item(
    *, owner_id: uuid.UUID, title: str = "thing", created_at: datetime | None = None
) -> Item:
    return Item(
        id=uuid.uuid4(),
        title=title,
        description="d",
        owner_id=owner_id,
        created_at=created_at or datetime.now(UTC),
    )


def test_insert_then_read_back(db: DBConnection) -> None:
    owner = _owner(db)
    item = _item(owner_id=owner.id)

    stored = item_repo.insert(conn=db, item=item)

    assert stored == item
    assert item_repo.get_by_id(conn=db, item_id=item.id) == item


def test_list_page_is_scoped_by_owner(db: DBConnection) -> None:
    owner = _owner(db)
    other = _owner(db)
    older = _item(
        owner_id=owner.id,
        title="older",
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    newer = _item(owner_id=owner.id, title="newer", created_at=datetime.now(UTC))
    item_repo.insert(conn=db, item=older)
    item_repo.insert(conn=db, item=newer)
    item_repo.insert(conn=db, item=_item(owner_id=other.id))

    scoped, scoped_count = item_repo.list_page(
        conn=db, owner_id=owner.id, skip=0, limit=100
    )
    everything, everything_count = item_repo.list_page(
        conn=db, owner_id=None, skip=0, limit=100
    )

    assert scoped_count == 2
    assert [item.id for item in scoped] == [newer.id, older.id]
    assert everything_count >= 3
    assert {item.id for item in everything} >= {older.id, newer.id}


def test_update_only_touches_supplied_columns(db: DBConnection) -> None:
    owner = _owner(db)
    item = _item(owner_id=owner.id)
    item_repo.insert(conn=db, item=item)

    updated = item_repo.update(conn=db, item_id=item.id, changes={"title": "renamed"})

    assert updated is not None
    assert updated.title == "renamed"
    assert updated.description == "d"
    assert updated.owner_id == owner.id


def test_update_missing_row_returns_none(db: DBConnection) -> None:
    assert (
        item_repo.update(conn=db, item_id=uuid.uuid4(), changes={"title": "x"}) is None
    )


def test_delete_reports_whether_a_row_existed(db: DBConnection) -> None:
    owner = _owner(db)
    item = _item(owner_id=owner.id)
    item_repo.insert(conn=db, item=item)

    assert item_repo.delete(conn=db, item_id=item.id) is True
    assert item_repo.delete(conn=db, item_id=item.id) is False
