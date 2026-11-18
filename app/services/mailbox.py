"""Mailbox use cases: poll the configured mailbox and read what was stored.

Polling is *incremental*: the remote provider exposes an opaque position token
(Gmail's `historyId`), which is stored per mailbox and advanced in the same
transaction as the messages it covers. A cycle therefore asks "what changed
since last time" instead of "give me the newest N again".

Polling is deliberately *not* part of a request path unless a caller asks for it
explicitly (`POST /mail/poll`). The same function backs the CLI entry point in
`app/poller.py`, which is where scheduled polling belongs.
"""

import uuid
from typing import Literal

from app.clients.gmail import HistoryExpired, MailClient
from app.core.db import DBConnection, commit
from app.domain.errors import ErrorCode, NotFound, PermissionDenied
from app.domain.mail import MailMessage, PollResult
from app.domain.models import User
from app.repositories import mail as mail_repo


def require_superuser(actor: User) -> None:
    """The shared mailbox is an administrative resource, not a user's own data."""
    if not actor.is_superuser:
        raise PermissionDenied(ErrorCode.INSUFFICIENT_PRIVILEGES)


def poll_new(*, conn: DBConnection, client: MailClient, limit: int) -> PollResult:
    """Store mail added since the last successful cycle."""
    profile = client.profile()
    mailbox = profile.address
    cursor = mail_repo.get_cursor(conn=conn, mailbox=mailbox)
    mode: Literal["full", "incremental"] = "incremental"

    if cursor is None:
        mode = "full"
        # Read the position *before* listing: anything arriving in between is
        # either in this listing or in the next history window, never neither.
        new_cursor = profile.cursor
        remote_ids = client.list_recent_ids(limit=limit)
    else:
        try:
            changes = client.changes_since(since=cursor)
        except HistoryExpired:
            # Gmail dropped the history window; start over from this position.
            mode = "full"
            new_cursor = profile.cursor
            remote_ids = client.list_recent_ids(limit=limit)
        else:
            new_cursor = changes.cursor
            remote_ids = list(changes.added)

    known = mail_repo.existing_ids(conn=conn, mailbox=mailbox, remote_ids=remote_ids)

    stored = 0
    skipped = 0
    for remote_id in remote_ids:
        if remote_id in known:
            skipped += 1
            continue
        mail = client.fetch(remote_id=remote_id)
        if mail_repo.insert(conn=conn, mailbox=mailbox, mail=mail) is None:
            # Lost a race with another poller; it stored this message already.
            skipped += 1
        else:
            stored += 1

    # Messages and cursor move together: a crash rolls back both, so the next
    # cycle re-reads the window instead of skipping it.
    mail_repo.set_cursor(conn=conn, mailbox=mailbox, cursor=new_cursor)
    commit(conn)

    return PollResult(
        mailbox=mailbox,
        mode=mode,
        listed=len(remote_ids),
        stored=stored,
        skipped=skipped,
        cursor=new_cursor,
    )


def list_messages(
    *, conn: DBConnection, actor: User, skip: int, limit: int
) -> tuple[list[MailMessage], int]:
    require_superuser(actor)
    return mail_repo.list_page(conn=conn, skip=skip, limit=limit)


def get_message(*, conn: DBConnection, actor: User, mail_id: uuid.UUID) -> MailMessage:
    require_superuser(actor)
    mail = mail_repo.get_by_id(conn=conn, mail_id=mail_id)
    if mail is None:
        raise NotFound(ErrorCode.MAIL_NOT_FOUND)
    return mail
