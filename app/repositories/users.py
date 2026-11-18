"""User persistence. SQL and row mapping only; no business rules."""

import uuid
from collections.abc import Mapping
from typing import Any, Final

from psycopg.errors import UniqueViolation
from psycopg.rows import DictRow

from app.core.db import DBConnection
from app.domain.errors import Conflict, ErrorCode
from app.domain.models import User
from app.repositories.common import update_row

COLUMNS: Final = "id, email, full_name, is_active, is_superuser, hashed_password, google_sub, created_at"
GOOGLE_SUB_INDEX: Final = "ix_user_google_sub"


def _to_user(row: DictRow) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        full_name=row["full_name"],
        is_active=row["is_active"],
        is_superuser=row["is_superuser"],
        hashed_password=row["hashed_password"],
        google_sub=row["google_sub"],
        created_at=row["created_at"],
    )


def get_by_id(*, conn: DBConnection, user_id: uuid.UUID) -> User | None:
    row = conn.execute(
        f'SELECT {COLUMNS} FROM "user" WHERE id = %s', (user_id,)
    ).fetchone()
    return _to_user(row) if row else None


def get_by_email(*, conn: DBConnection, email: str) -> User | None:
    row = conn.execute(
        f'SELECT {COLUMNS} FROM "user" WHERE email = %s', (email,)
    ).fetchone()
    return _to_user(row) if row else None


def get_by_google_sub(*, conn: DBConnection, google_sub: str) -> User | None:
    row = conn.execute(
        f'SELECT {COLUMNS} FROM "user" WHERE google_sub = %s', (google_sub,)
    ).fetchone()
    return _to_user(row) if row else None


def insert(*, conn: DBConnection, user: User) -> User:
    try:
        row = conn.execute(
            f'INSERT INTO "user" ({COLUMNS})'
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            f" RETURNING {COLUMNS}",
            (
                user.id,
                user.email,
                user.full_name,
                user.is_active,
                user.is_superuser,
                user.hashed_password,
                user.google_sub,
                user.created_at,
            ),
        ).fetchone()
    except UniqueViolation as exc:
        # The service pre-checks, but a concurrent request can still win the race.
        if exc.diag.constraint_name == GOOGLE_SUB_INDEX:
            raise Conflict(ErrorCode.GOOGLE_ACCOUNT_TAKEN) from exc
        raise Conflict(ErrorCode.EMAIL_TAKEN_ON_CREATE) from exc
    assert row is not None
    return _to_user(row)


def update(
    *, conn: DBConnection, user_id: uuid.UUID, changes: Mapping[str, Any]
) -> User | None:
    row = update_row(
        conn=conn,
        table="user",
        row_id=user_id,
        changes=changes,
        returning=COLUMNS,
    )
    return _to_user(row) if row else None


def delete(*, conn: DBConnection, user_id: uuid.UUID) -> bool:
    cursor = conn.execute('DELETE FROM "user" WHERE id = %s', (user_id,))
    return cursor.rowcount > 0


def list_page(*, conn: DBConnection, skip: int, limit: int) -> tuple[list[User], int]:
    total = conn.execute('SELECT count(*) AS total FROM "user"').fetchone()
    rows = conn.execute(
        f'SELECT {COLUMNS} FROM "user" ORDER BY created_at DESC OFFSET %s LIMIT %s',
        (skip, limit),
    ).fetchall()
    return [_to_user(row) for row in rows], (total["total"] if total else 0)
