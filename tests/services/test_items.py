import uuid
from typing import Any

import pytest

from app.domain.commands import CreateItem, UpdateItem
from app.domain.errors import ErrorCode, NotFound, PermissionDenied
from app.services import items as item_service
from tests.fakes import CONN, install_item_repo, make_item, make_user


def test_owner_can_create_item(monkeypatch: Any) -> None:
    owner = make_user()
    repo, commits = install_item_repo(monkeypatch)

    item = item_service.create_item(
        conn=CONN, cmd=CreateItem(title="thing", description="d"), actor=owner
    )

    assert item.owner_id == owner.id
    assert item.title == "thing"
    assert repo.items[item.id] == item
    assert len(commits) == 1


def test_owner_can_read_own_item(monkeypatch: Any) -> None:
    owner = make_user()
    item = make_item(owner_id=owner.id)
    install_item_repo(monkeypatch, [item])

    assert item_service.get_item(conn=CONN, item_id=item.id, actor=owner) == item


def test_missing_item_raises_not_found(monkeypatch: Any) -> None:
    install_item_repo(monkeypatch)

    with pytest.raises(NotFound) as exc:
        item_service.get_item(conn=CONN, item_id=uuid.uuid4(), actor=make_user())

    assert exc.value.code is ErrorCode.ITEM_NOT_FOUND


def test_other_user_cannot_read_item(monkeypatch: Any) -> None:
    owner = make_user(email="owner@example.com")
    stranger = make_user(email="stranger@example.com")
    item = make_item(owner_id=owner.id)
    install_item_repo(monkeypatch, [item])

    with pytest.raises(PermissionDenied) as exc:
        item_service.get_item(conn=CONN, item_id=item.id, actor=stranger)

    assert exc.value.code is ErrorCode.ITEM_PERMISSION_DENIED


def test_superuser_can_read_any_item(monkeypatch: Any) -> None:
    item = make_item(owner_id=uuid.uuid4())
    install_item_repo(monkeypatch, [item])

    found = item_service.get_item(
        conn=CONN, item_id=item.id, actor=make_user(is_superuser=True)
    )

    assert found == item


def test_listing_is_scoped_for_normal_users(monkeypatch: Any) -> None:
    owner = make_user(email="owner@example.com")
    stranger = make_user(email="stranger@example.com")
    mine = make_item(owner_id=owner.id, title="mine")
    install_item_repo(monkeypatch, [mine])

    owner_items, owner_count = item_service.list_items(
        conn=CONN, actor=owner, skip=0, limit=100
    )
    stranger_items, stranger_count = item_service.list_items(
        conn=CONN, actor=stranger, skip=0, limit=100
    )

    assert owner_count == 1 and owner_items == [mine]
    assert stranger_count == 0 and stranger_items == []


def test_superuser_listing_sees_everything(monkeypatch: Any) -> None:
    install_item_repo(
        monkeypatch,
        [make_item(owner_id=uuid.uuid4()), make_item(owner_id=uuid.uuid4())],
    )

    items, count = item_service.list_items(
        conn=CONN, actor=make_user(is_superuser=True), skip=0, limit=100
    )

    assert count == 2
    assert len(items) == 2


def test_partial_update_preserves_other_fields(monkeypatch: Any) -> None:
    owner = make_user()
    item = make_item(owner_id=owner.id, title="before", description="keep me")
    repo, commits = install_item_repo(monkeypatch, [item])

    updated = item_service.update_item(
        conn=CONN,
        item_id=item.id,
        cmd=UpdateItem(title="after", fields_set=frozenset({"title"})),
        actor=owner,
    )

    assert updated.title == "after"
    assert updated.description == "keep me"
    assert repo.items[item.id].description == "keep me"
    assert len(commits) == 1


def test_other_user_cannot_update_item(monkeypatch: Any) -> None:
    owner = make_user(email="owner@example.com")
    stranger = make_user(email="stranger@example.com")
    item = make_item(owner_id=owner.id)
    install_item_repo(monkeypatch, [item])

    with pytest.raises(PermissionDenied):
        item_service.update_item(
            conn=CONN,
            item_id=item.id,
            cmd=UpdateItem(title="hijack", fields_set=frozenset({"title"})),
            actor=stranger,
        )


def test_owner_can_delete_item(monkeypatch: Any) -> None:
    owner = make_user()
    item = make_item(owner_id=owner.id)
    repo, commits = install_item_repo(monkeypatch, [item])

    item_service.delete_item(conn=CONN, item_id=item.id, actor=owner)

    assert item.id not in repo.items
    assert len(commits) == 1


def test_other_user_cannot_delete_item(monkeypatch: Any) -> None:
    owner = make_user(email="owner@example.com")
    stranger = make_user(email="stranger@example.com")
    item = make_item(owner_id=owner.id)
    install_item_repo(monkeypatch, [item])

    with pytest.raises(PermissionDenied):
        item_service.delete_item(conn=CONN, item_id=item.id, actor=stranger)
