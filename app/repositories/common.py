"""SQL helpers shared by repositories."""

import uuid
from collections.abc import Mapping
from typing import Any, LiteralString

from psycopg import sql
from psycopg.rows import DictRow

from app.core.db import DBConnection


def update_row(
    *,
    conn: DBConnection,
    table: LiteralString,
    row_id: uuid.UUID,
    changes: Mapping[str, Any],
    returning: LiteralString,
) -> DictRow | None:
    """Update only the supplied columns; identifiers are quoted, values bound."""
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
