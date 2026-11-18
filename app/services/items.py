"""Item use cases: ownership rules live here, not in the routes."""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.db import DBConnection, commit
from app.domain.commands import CreateItem, UpdateItem
from app.domain.errors import ErrorCode, NotFound, PermissionDenied
from app.domain.models import Item, User
from app.repositories import items as item_repo


def _load_for_actor(*, conn: DBConnection, item_id: uuid.UUID, actor: User) -> Item:
    item = item_repo.get_by_id(conn=conn, item_id=item_id)
    if not item:
        raise NotFound(ErrorCode.ITEM_NOT_FOUND)
    if not actor.is_superuser and item.owner_id != actor.id:
        raise PermissionDenied(ErrorCode.ITEM_PERMISSION_DENIED)
    return item


def create_item(*, conn: DBConnection, cmd: CreateItem, actor: User) -> Item:
    item = Item(
        id=uuid.uuid4(),
        title=cmd.title,
        description=cmd.description,
        owner_id=actor.id,
        created_at=datetime.now(UTC),
    )
    created = item_repo.insert(conn=conn, item=item)
    commit(conn)
    return created


def list_items(
    *, conn: DBConnection, actor: User, skip: int, limit: int
) -> tuple[list[Item], int]:
    owner_id = None if actor.is_superuser else actor.id
    return item_repo.list_page(conn=conn, owner_id=owner_id, skip=skip, limit=limit)


def get_item(*, conn: DBConnection, item_id: uuid.UUID, actor: User) -> Item:
    return _load_for_actor(conn=conn, item_id=item_id, actor=actor)


def update_item(
    *, conn: DBConnection, item_id: uuid.UUID, cmd: UpdateItem, actor: User
) -> Item:
    _load_for_actor(conn=conn, item_id=item_id, actor=actor)
    changes: dict[str, Any] = {}
    if "title" in cmd.fields_set and cmd.title is not None:
        changes["title"] = cmd.title
    if "description" in cmd.fields_set:
        changes["description"] = cmd.description
    updated = item_repo.update(conn=conn, item_id=item_id, changes=changes)
    if updated is None:
        raise NotFound(ErrorCode.ITEM_NOT_FOUND)
    commit(conn)
    return updated


def delete_item(*, conn: DBConnection, item_id: uuid.UUID, actor: User) -> None:
    _load_for_actor(conn=conn, item_id=item_id, actor=actor)
    item_repo.delete(conn=conn, item_id=item_id)
    commit(conn)
