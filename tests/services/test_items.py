"""Service-level tests for item ownership rules (no HTTP involved)."""

import uuid

import pytest

from app.core.db import DBConnection
from app.domain.commands import CreateItem, UpdateItem
from app.domain.errors import NotFound, PermissionDenied
from app.services import items as item_service
from tests.utils.user import create_test_user
from tests.utils.utils import random_email, random_lower_string


def _user(db: DBConnection, *, is_superuser: bool = False):
    return create_test_user(
        db,
        email=random_email(),
        password=random_lower_string(),
        is_superuser=is_superuser,
    )


def test_owner_can_read_own_item(db: DBConnection) -> None:
    owner = _user(db)
    item = item_service.create_item(
        conn=db, cmd=CreateItem(title="thing", description="d"), actor=owner
    )

    found = item_service.get_item(conn=db, item_id=item.id, actor=owner)

    assert found == item


def test_other_user_cannot_read_item(db: DBConnection) -> None:
    owner = _user(db)
    stranger = _user(db)
    item = item_service.create_item(conn=db, cmd=CreateItem(title="thing"), actor=owner)

    with pytest.raises(PermissionDenied):
        item_service.get_item(conn=db, item_id=item.id, actor=stranger)


def test_other_user_cannot_update_item(db: DBConnection) -> None:
    owner = _user(db)
    stranger = _user(db)
    item = item_service.create_item(conn=db, cmd=CreateItem(title="thing"), actor=owner)

    with pytest.raises(PermissionDenied):
        item_service.update_item(
            conn=db,
            item_id=item.id,
            cmd=UpdateItem(title="hijack", fields_set=frozenset({"title"})),
            actor=stranger,
        )


def test_superuser_can_access_any_item(db: DBConnection) -> None:
    owner = _user(db)
    admin = _user(db, is_superuser=True)
    item = item_service.create_item(conn=db, cmd=CreateItem(title="thing"), actor=owner)

    assert item_service.get_item(conn=db, item_id=item.id, actor=admin) == item


def test_partial_update_preserves_other_fields(db: DBConnection) -> None:
    owner = _user(db)
    item = item_service.create_item(
        conn=db,
        cmd=CreateItem(title="before", description="keep me"),
        actor=owner,
    )

    updated = item_service.update_item(
        conn=db,
        item_id=item.id,
        cmd=UpdateItem(title="after", fields_set=frozenset({"title"})),
        actor=owner,
    )

    assert updated.title == "after"
    assert updated.description == "keep me"


def test_listing_is_scoped_for_normal_users(db: DBConnection) -> None:
    owner = _user(db)
    stranger = _user(db)
    item = item_service.create_item(conn=db, cmd=CreateItem(title="mine"), actor=owner)

    owner_items, owner_count = item_service.list_items(
        conn=db, actor=owner, skip=0, limit=100
    )
    stranger_items, stranger_count = item_service.list_items(
        conn=db, actor=stranger, skip=0, limit=100
    )

    assert item.id in {i.id for i in owner_items}
    assert owner_count == len(owner_items)
    assert stranger_count == 0
    assert stranger_items == []


def test_delete_item(db: DBConnection) -> None:
    owner = _user(db)
    item = item_service.create_item(conn=db, cmd=CreateItem(title="thing"), actor=owner)

    item_service.delete_item(conn=db, item_id=item.id, actor=owner)

    with pytest.raises(NotFound):
        item_service.get_item(conn=db, item_id=item.id, actor=owner)


def test_missing_item_raises_not_found(db: DBConnection) -> None:
    actor = _user(db)

    with pytest.raises(NotFound):
        item_service.get_item(conn=db, item_id=uuid.uuid4(), actor=actor)
