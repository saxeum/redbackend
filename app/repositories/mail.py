"""Mail persistence. SQL and row mapping only; no business rules."""

import uuid
from collections.abc import Sequence
from typing import Final

from psycopg.rows import DictRow

from app.core.db import DBConnection
from app.domain.mail import FetchedMail, MailMessage

COLUMNS: Final = (
    "id, mailbox, remote_id, thread_id, from_address, subject, snippet, body, "
    "received_at, created_at"
)
INSERT_COLUMNS: Final = (
    "id, mailbox, remote_id, thread_id, from_address, subject, snippet, body, "
    "received_at"
)


def _to_mail(row: DictRow) -> MailMessage:
    return MailMessage(
        id=row["id"],
        mailbox=row["mailbox"],
        remote_id=row["remote_id"],
        thread_id=row["thread_id"],
        from_address=row["from_address"],
        subject=row["subject"],
        snippet=row["snippet"],
        body=row["body"],
        received_at=row["received_at"],
        created_at=row["created_at"],
    )


def insert(
    *, conn: DBConnection, mailbox: str, mail: FetchedMail
) -> MailMessage | None:
    """Store a message once per mailbox; returns None when it is already there."""
    row = conn.execute(
        f"INSERT INTO mail_message ({INSERT_COLUMNS})"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
        " ON CONFLICT (mailbox, remote_id) DO NOTHING"
        f" RETURNING {COLUMNS}",
        (
            uuid.uuid4(),
            mailbox,
            mail.remote_id,
            mail.thread_id,
            mail.from_address,
            mail.subject,
            mail.snippet,
            mail.body,
            mail.received_at,
        ),
    ).fetchone()
    return _to_mail(row) if row else None


def existing_ids(
    *, conn: DBConnection, mailbox: str, remote_ids: Sequence[str]
) -> set[str]:
    if not remote_ids:
        return set()
    rows = conn.execute(
        "SELECT remote_id FROM mail_message"
        " WHERE mailbox = %s AND remote_id = ANY(%s::text[])",
        (mailbox, list(remote_ids)),
    ).fetchall()
    return {row["remote_id"] for row in rows}


def get_by_id(*, conn: DBConnection, mail_id: uuid.UUID) -> MailMessage | None:
    row = conn.execute(
        f"SELECT {COLUMNS} FROM mail_message WHERE id = %s", (mail_id,)
    ).fetchone()
    return _to_mail(row) if row else None


def list_page(
    *, conn: DBConnection, skip: int, limit: int
) -> tuple[list[MailMessage], int]:
    total = conn.execute("SELECT count(*) AS total FROM mail_message").fetchone()
    rows = conn.execute(
        f"SELECT {COLUMNS} FROM mail_message"
        " ORDER BY received_at DESC, created_at DESC OFFSET %s LIMIT %s",
        (skip, limit),
    ).fetchall()
    return [_to_mail(row) for row in rows], (total["total"] if total else 0)


def get_cursor(*, conn: DBConnection, mailbox: str) -> str | None:
    row = conn.execute(
        "SELECT cursor FROM mailbox_cursor WHERE mailbox = %s", (mailbox,)
    ).fetchone()
    return row["cursor"] if row else None


def set_cursor(*, conn: DBConnection, mailbox: str, cursor: str) -> None:
    conn.execute(
        "INSERT INTO mailbox_cursor (mailbox, cursor, updated_at) VALUES (%s, %s, now())"
        " ON CONFLICT (mailbox) DO UPDATE"
        " SET cursor = EXCLUDED.cursor, updated_at = now()",
        (mailbox, cursor),
    )
