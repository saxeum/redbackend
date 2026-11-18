"""In-memory test doubles for the layer above the one under test.

Controllers mock services, services mock repositories. The fakes mirror the
repository function signatures exactly so a drifting interface fails loudly.
"""

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

from app.core.db import DBConnection
from app.domain.errors import Conflict, ErrorCode
from app.domain.models import Item, User

# Fakes never touch the connection; this keeps the call signatures honest.
CONN = cast(DBConnection, object())


def make_user(
    *,
    email: str = "user@example.com",
    hashed_password: str | None = "hash",
    full_name: str | None = None,
    is_active: bool = True,
    is_superuser: bool = False,
    google_sub: str | None = None,
    user_id: uuid.UUID | None = None,
) -> User:
    return User(
        id=user_id or uuid.uuid4(),
        email=email,
        full_name=full_name,
        is_active=is_active,
        is_superuser=is_superuser,
        hashed_password=hashed_password,
        google_sub=google_sub,
        created_at=datetime.now(UTC),
    )


def make_item(
    *,
    title: str = "item",
    description: str | None = None,
    owner_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
) -> Item:
    return Item(
        id=item_id or uuid.uuid4(),
        title=title,
        description=description,
        owner_id=owner_id or uuid.uuid4(),
        created_at=datetime.now(UTC),
    )


class FakeUserRepository:
    def __init__(self, users: list[User] | None = None) -> None:
        self.users: dict[uuid.UUID, User] = {user.id: user for user in users or []}
        self.deleted: list[uuid.UUID] = []

    def get_by_id(self, *, conn: DBConnection, user_id: uuid.UUID) -> User | None:
        return self.users.get(user_id)

    def get_by_email(self, *, conn: DBConnection, email: str) -> User | None:
        return next((u for u in self.users.values() if u.email == email), None)

    def get_by_google_sub(self, *, conn: DBConnection, google_sub: str) -> User | None:
        return next(
            (u for u in self.users.values() if u.google_sub == google_sub), None
        )

    def insert(self, *, conn: DBConnection, user: User) -> User:
        if self.get_by_email(conn=conn, email=user.email):
            raise Conflict(ErrorCode.EMAIL_TAKEN_ON_CREATE)
        if user.google_sub and self.get_by_google_sub(
            conn=conn, google_sub=user.google_sub
        ):
            raise Conflict(ErrorCode.GOOGLE_ACCOUNT_TAKEN)
        self.users[user.id] = user
        return user

    def update(
        self, *, conn: DBConnection, user_id: uuid.UUID, changes: dict[str, Any]
    ) -> User | None:
        current = self.users.get(user_id)
        if current is None:
            return None
        updated = replace(current, **changes)
        self.users[user_id] = updated
        return updated

    def delete(self, *, conn: DBConnection, user_id: uuid.UUID) -> bool:
        self.deleted.append(user_id)
        return self.users.pop(user_id, None) is not None

    def list_page(
        self, *, conn: DBConnection, skip: int, limit: int
    ) -> tuple[list[User], int]:
        ordered = sorted(self.users.values(), key=lambda u: u.created_at, reverse=True)
        return ordered[skip : skip + limit], len(ordered)


class FakeItemRepository:
    def __init__(self, items: list[Item] | None = None) -> None:
        self.items: dict[uuid.UUID, Item] = {item.id: item for item in items or []}
        self.deleted: list[uuid.UUID] = []

    def get_by_id(self, *, conn: DBConnection, item_id: uuid.UUID) -> Item | None:
        return self.items.get(item_id)

    def insert(self, *, conn: DBConnection, item: Item) -> Item:
        self.items[item.id] = item
        return item

    def update(
        self, *, conn: DBConnection, item_id: uuid.UUID, changes: dict[str, Any]
    ) -> Item | None:
        current = self.items.get(item_id)
        if current is None:
            return None
        updated = replace(current, **changes)
        self.items[item_id] = updated
        return updated

    def delete(self, *, conn: DBConnection, item_id: uuid.UUID) -> bool:
        self.deleted.append(item_id)
        return self.items.pop(item_id, None) is not None

    def list_page(
        self,
        *,
        conn: DBConnection,
        owner_id: uuid.UUID | None,
        skip: int,
        limit: int,
    ) -> tuple[list[Item], int]:
        visible = [
            item
            for item in self.items.values()
            if owner_id is None or item.owner_id == owner_id
        ]
        ordered = sorted(visible, key=lambda i: i.created_at, reverse=True)
        return ordered[skip : skip + limit], len(ordered)


def install_user_repo(
    monkeypatch: Any, users: list[User] | None = None
) -> tuple[FakeUserRepository, list[Any]]:
    """Replace the repository and the commit hook used by the user service."""
    repo = FakeUserRepository(users)
    commits: list[Any] = []
    monkeypatch.setattr("app.services.users.user_repo", repo)
    monkeypatch.setattr("app.services.users.commit", commits.append)
    return repo, commits


def install_item_repo(
    monkeypatch: Any, items: list[Item] | None = None
) -> tuple[FakeItemRepository, list[Any]]:
    repo = FakeItemRepository(items)
    commits: list[Any] = []
    monkeypatch.setattr("app.services.items.item_repo", repo)
    monkeypatch.setattr("app.services.items.commit", commits.append)
    return repo, commits
