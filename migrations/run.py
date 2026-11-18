"""Apply pending SQL migrations.

Every `*.sql` file in this directory is applied once, in filename order, and
recorded in the `schema_migrations` table. Run it with:

    make db-migrate        # or: uv run python -m migrations.run

Migrations are deliberately out of band: the API container never runs them.
"""

from pathlib import Path

import psycopg

from app.core.config import settings

MIGRATIONS_DIR = Path(__file__).resolve().parent

CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


def discover() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def main() -> int:
    applied: set[str] = set()
    pending: list[Path] = []
    with psycopg.connect(str(settings.DATABASE_URL)) as conn:
        conn.execute(CREATE_MIGRATIONS_TABLE)
        applied = {
            row[0] for row in conn.execute("SELECT version FROM schema_migrations")
        }
        pending = [path for path in discover() if path.stem not in applied]
        for path in pending:
            print(f"applying {path.name}")
            conn.execute(path.read_bytes())
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,)
            )
        conn.commit()

    print(f"{len(pending)} applied, {len(applied)} already applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
