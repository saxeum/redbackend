"""In-memory test doubles for the layer above the one under test.

Controllers mock services, services mock repositories. The fakes mirror the
repository function signatures exactly so a drifting interface fails loudly.
"""

import uuid
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

from app.clients.gmail import HistoryExpired
from app.core.db import DBConnection
from app.domain.errors import Conflict, ErrorCode
from app.domain.mail import (
    FetchedMail,
    MailboxChanges,
    MailboxProfile,
    MailMessage,
)
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


# --- mail -----------------------------------------------------------------


def make_fetched(
    *,
    remote_id: str = "remote-1",
    thread_id: str | None = None,
    from_address: str = "customer@example.com",
    subject: str | None = "Hello",
    snippet: str = "a short snippet",
    body: str = "the body",
    received_at: datetime | None = None,
) -> FetchedMail:
    return FetchedMail(
        remote_id=remote_id,
        thread_id=thread_id or f"thread-{remote_id}",
        from_address=from_address,
        subject=subject,
        snippet=snippet,
        body=body,
        received_at=received_at or datetime.now(UTC),
    )


def make_mail(
    *,
    mailbox: str = "inbox@example.com",
    fetched: FetchedMail | None = None,
    mail_id: uuid.UUID | None = None,
    subject: str | None = None,
    snippet: str | None = None,
    body: str | None = None,
) -> MailMessage:
    source = fetched or make_fetched()
    if subject is not None:
        source = replace(source, subject=subject)
    if snippet is not None:
        source = replace(source, snippet=snippet)
    if body is not None:
        source = replace(source, body=body)
    return MailMessage(
        id=mail_id or uuid.uuid4(),
        mailbox=mailbox,
        remote_id=source.remote_id,
        thread_id=source.thread_id,
        from_address=source.from_address,
        subject=source.subject,
        snippet=source.snippet,
        body=source.body,
        received_at=source.received_at,
        created_at=datetime.now(UTC),
    )


class FakeMailRepository:
    def __init__(self, messages: list[MailMessage] | None = None) -> None:
        self.messages: dict[uuid.UUID, MailMessage] = {
            message.id: message for message in messages or []
        }
        self.inserted: list[MailMessage] = []
        self.cursors: dict[str, str] = {}

    def insert(
        self, *, conn: DBConnection, mailbox: str, mail: FetchedMail
    ) -> MailMessage | None:
        duplicate = any(
            stored.mailbox == mailbox and stored.remote_id == mail.remote_id
            for stored in self.messages.values()
        )
        if duplicate:
            return None
        message = make_mail(mailbox=mailbox, fetched=mail)
        self.messages[message.id] = message
        self.inserted.append(message)
        return message

    def existing_ids(
        self, *, conn: DBConnection, mailbox: str, remote_ids: Sequence[str]
    ) -> set[str]:
        wanted = set(remote_ids)
        return {
            stored.remote_id
            for stored in self.messages.values()
            if stored.mailbox == mailbox and stored.remote_id in wanted
        }

    def get_by_id(
        self, *, conn: DBConnection, mail_id: uuid.UUID
    ) -> MailMessage | None:
        return self.messages.get(mail_id)

    def list_page(
        self, *, conn: DBConnection, skip: int, limit: int
    ) -> tuple[list[MailMessage], int]:
        ordered = sorted(
            self.messages.values(), key=lambda m: m.received_at, reverse=True
        )
        return ordered[skip : skip + limit], len(ordered)

    def get_cursor(self, *, conn: DBConnection, mailbox: str) -> str | None:
        return self.cursors.get(mailbox)

    def set_cursor(self, *, conn: DBConnection, mailbox: str, cursor: str) -> None:
        self.cursors[mailbox] = cursor


class FakeMailClient:
    """Stands in for the Gmail adapter in service tests.

    `messages` is what the mailbox holds; `added` is what the provider reports
    as changed since the stored cursor. `expired` simulates the history window
    rolling past the cursor.
    """

    def __init__(
        self,
        *,
        address: str = "inbox@example.com",
        cursor: str = "100",
        messages: list[FetchedMail] | None = None,
        added: list[str] | None = None,
        expired: bool = False,
    ) -> None:
        self.address = address
        self.cursor = cursor
        self.messages: dict[str, FetchedMail] = {
            message.remote_id: message for message in messages or []
        }
        self.added = list(added or [])
        self.expired = expired
        self.fetched: list[str] = []

    def profile(self) -> MailboxProfile:
        return MailboxProfile(address=self.address, cursor=self.cursor)

    def list_recent_ids(self, *, limit: int) -> list[str]:
        return list(self.messages)[:limit]

    def changes_since(self, *, since: str) -> MailboxChanges:
        if self.expired:
            raise HistoryExpired(since)
        return MailboxChanges(added=tuple(self.added), cursor=self.cursor)

    def fetch(self, *, remote_id: str) -> FetchedMail:
        self.fetched.append(remote_id)
        return self.messages[remote_id]


def install_mail_repo(
    monkeypatch: Any, messages: list[MailMessage] | None = None
) -> tuple[FakeMailRepository, list[Any]]:
    repo = FakeMailRepository(messages)
    commits: list[Any] = []
    monkeypatch.setattr("app.services.mailbox.mail_repo", repo)
    monkeypatch.setattr("app.services.mailbox.commit", commits.append)
    return repo, commits
