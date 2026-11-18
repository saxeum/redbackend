"""Item persistence. SQL and row mapping only; no business rules."""

import uuid
from collections.abc import Mapping
from typing import Any, Final

from psycopg.rows import DictRow

from app.core.db import DBConnection
from app.domain.models import Item
from app.repositories.common import update_row

COLUMNS: Final = "id, title, description, owner_id, created_at"


def _to_item(row: DictRow) -> Item:
    return Item(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        owner_id=row["owner_id"],
        created_at=row["created_at"],
    )


def get_by_id(*, conn: DBConnection, item_id: uuid.UUID) -> Item | None:
    row = conn.execute(
        f"SELECT {COLUMNS} FROM item WHERE id = %s", (item_id,)
    ).fetchone()
    return _to_item(row) if row else None


def insert(*, conn: DBConnection, item: Item) -> Item:
    row = conn.execute(
        f"INSERT INTO item ({COLUMNS}) VALUES (%s, %s, %s, %s, %s) RETURNING {COLUMNS}",
        (
            item.id,
            item.title,
            item.description,
            item.owner_id,
            item.created_at,
        ),
    ).fetchone()
    assert row is not None
    return _to_item(row)


def update(
    *, conn: DBConnection, item_id: uuid.UUID, changes: Mapping[str, Any]
) -> Item | None:
    row = update_row(
        conn=conn,
        table="item",
        row_id=item_id,
        changes=changes,
        returning=COLUMNS,
    )
    return _to_item(row) if row else None


def delete(*, conn: DBConnection, item_id: uuid.UUID) -> bool:
    cursor = conn.execute("DELETE FROM item WHERE id = %s", (item_id,))
    return cursor.rowcount > 0


def list_page(
    *,
    conn: DBConnection,
    owner_id: uuid.UUID | None,
    skip: int,
    limit: int,
) -> tuple[list[Item], int]:
    if owner_id is None:
        total = conn.execute("SELECT count(*) AS total FROM item").fetchone()
        rows = conn.execute(
            f"SELECT {COLUMNS} FROM item ORDER BY created_at DESC OFFSET %s LIMIT %s",
            (skip, limit),
        ).fetchall()
    else:
        total = conn.execute(
            "SELECT count(*) AS total FROM item WHERE owner_id = %s", (owner_id,)
        ).fetchone()
        rows = conn.execute(
            f"SELECT {COLUMNS} FROM item WHERE owner_id = %s"
            " ORDER BY created_at DESC OFFSET %s LIMIT %s",
            (owner_id, skip, limit),
        ).fetchall()
    return [_to_item(row) for row in rows], (total["total"] if total else 0)
