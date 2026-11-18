import uuid
from datetime import UTC, datetime
from typing import Any, Final, LiteralString

from psycopg import sql
from psycopg.rows import DictRow

from app.core.db import DBConnection
from app.core.security import get_password_hash, verify_password
from app.models import (
    ItemCreate,
    ItemPublic,
    ItemUpdate,
    UserCreate,
    UserRow,
    UserUpdate,
    UserUpdateMe,
)

USER_COLUMNS: Final = (
    "id, email, is_active, is_superuser, full_name, hashed_password, created_at"
)
ITEM_COLUMNS: Final = "id, title, description, owner_id, created_at"


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def _update_row(
    *,
    conn: DBConnection,
    table: str,
    row_id: uuid.UUID,
    changes: dict[str, Any],
    returning: LiteralString,
) -> DictRow | None:
    """Update only the given columns; column names are quoted as identifiers."""
    if not changes:
        return conn.execute(
            sql.SQL("SELECT {columns} FROM {table} WHERE id = %s").format(
                columns=sql.SQL(returning), table=sql.Identifier(table)
            ),
            (row_id,),
        ).fetchone()

    assignments = sql.SQL(", ").join(
        sql.SQL("{} = %s").format(sql.Identifier(column)) for column in changes
    )
    return conn.execute(
        sql.SQL(
            "UPDATE {table} SET {assignments} WHERE id = %s RETURNING {columns}"
        ).format(
            table=sql.Identifier(table),
            assignments=assignments,
            columns=sql.SQL(returning),
        ),
        (*changes.values(), row_id),
    ).fetchone()


def get_user_by_email(*, conn: DBConnection, email: str) -> UserRow | None:
    row = conn.execute(
        f'SELECT {USER_COLUMNS} FROM "user" WHERE email = %s', (email,)
    ).fetchone()
    return UserRow.model_validate(row) if row else None


def get_user_by_id(*, conn: DBConnection, user_id: uuid.UUID) -> UserRow | None:
    row = conn.execute(
        f'SELECT {USER_COLUMNS} FROM "user" WHERE id = %s', (user_id,)
    ).fetchone()
    return UserRow.model_validate(row) if row else None


def create_user(*, conn: DBConnection, user_create: UserCreate) -> UserRow:
    row = conn.execute(
        f'INSERT INTO "user" ({USER_COLUMNS})'
        " VALUES (%s, %s, %s, %s, %s, %s, %s)"
        f" RETURNING {USER_COLUMNS}",
        (
            uuid.uuid4(),
            str(user_create.email),
            user_create.is_active,
            user_create.is_superuser,
            user_create.full_name,
            get_password_hash(user_create.password),
            datetime.now(UTC),
        ),
    ).fetchone()
    assert row is not None
    return UserRow.model_validate(row)


def update_user(
    *,
    conn: DBConnection,
    user_id: uuid.UUID,
    user_in: UserUpdate | UserUpdateMe,
) -> UserRow | None:
    changes = user_in.model_dump(exclude_unset=True)
    if "password" in changes:
        changes["hashed_password"] = get_password_hash(changes.pop("password"))
    row = _update_row(
        conn=conn,
        table="user",
        row_id=user_id,
        changes=changes,
        returning=USER_COLUMNS,
    )
    return UserRow.model_validate(row) if row else None


def set_user_password(*, conn: DBConnection, user_id: uuid.UUID, password: str) -> None:
    conn.execute(
        'UPDATE "user" SET hashed_password = %s WHERE id = %s',
        (get_password_hash(password), user_id),
    )


def delete_user(*, conn: DBConnection, user_id: uuid.UUID) -> bool:
    cursor = conn.execute('DELETE FROM "user" WHERE id = %s', (user_id,))
    return cursor.rowcount > 0


def list_users(
    *, conn: DBConnection, skip: int, limit: int
) -> tuple[list[UserRow], int]:
    total = conn.execute('SELECT count(*) AS total FROM "user"').fetchone()
    rows = conn.execute(
        f'SELECT {USER_COLUMNS} FROM "user"'
        " ORDER BY created_at DESC OFFSET %s LIMIT %s",
        (skip, limit),
    ).fetchall()
    return [UserRow.model_validate(row) for row in rows], (
        total["total"] if total else 0
    )


def authenticate(*, conn: DBConnection, email: str, password: str) -> UserRow | None:
    db_user = get_user_by_email(conn=conn, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when the
        # user doesn't exist, so responses look the same either way.
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        conn.execute(
            'UPDATE "user" SET hashed_password = %s WHERE id = %s',
            (updated_password_hash, db_user.id),
        )
        db_user.hashed_password = updated_password_hash
    return db_user


def create_item(
    *, conn: DBConnection, item_in: ItemCreate, owner_id: uuid.UUID
) -> ItemPublic:
    row = conn.execute(
        f"INSERT INTO item ({ITEM_COLUMNS})"
        " VALUES (%s, %s, %s, %s, %s)"
        f" RETURNING {ITEM_COLUMNS}",
        (
            uuid.uuid4(),
            item_in.title,
            item_in.description,
            owner_id,
            datetime.now(UTC),
        ),
    ).fetchone()
    assert row is not None
    return ItemPublic.model_validate(row)


def get_item(*, conn: DBConnection, item_id: uuid.UUID) -> ItemPublic | None:
    row = conn.execute(
        f"SELECT {ITEM_COLUMNS} FROM item WHERE id = %s", (item_id,)
    ).fetchone()
    return ItemPublic.model_validate(row) if row else None


def update_item(
    *, conn: DBConnection, item_id: uuid.UUID, item_in: ItemUpdate
) -> ItemPublic | None:
    row = _update_row(
        conn=conn,
        table="item",
        row_id=item_id,
        changes=item_in.model_dump(exclude_unset=True),
        returning=ITEM_COLUMNS,
    )
    return ItemPublic.model_validate(row) if row else None


def delete_item(*, conn: DBConnection, item_id: uuid.UUID) -> bool:
    cursor = conn.execute("DELETE FROM item WHERE id = %s", (item_id,))
    return cursor.rowcount > 0


def list_items(
    *,
    conn: DBConnection,
    owner_id: uuid.UUID | None,
    skip: int,
    limit: int,
) -> tuple[list[ItemPublic], int]:
    if owner_id is None:
        total = conn.execute("SELECT count(*) AS total FROM item").fetchone()
        rows = conn.execute(
            f"SELECT {ITEM_COLUMNS} FROM item"
            " ORDER BY created_at DESC OFFSET %s LIMIT %s",
            (skip, limit),
        ).fetchall()
    else:
        total = conn.execute(
            "SELECT count(*) AS total FROM item WHERE owner_id = %s", (owner_id,)
        ).fetchone()
        rows = conn.execute(
            f"SELECT {ITEM_COLUMNS} FROM item WHERE owner_id = %s"
            " ORDER BY created_at DESC OFFSET %s LIMIT %s",
            (owner_id, skip, limit),
        ).fetchall()
    return (
        [ItemPublic.model_validate(row) for row in rows],
        total["total"] if total else 0,
    )
