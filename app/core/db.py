import atexit

from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

from app.core.config import settings

# Rows come back as dicts so they can be handed straight to Pydantic models.
DBConnection = Connection[DictRow]

pool = ConnectionPool(
    conninfo=str(settings.DATABASE_URL),
    min_size=1,
    # 4 uvicorn workers x 10 = 40 connections, below Postgres' default max of 100.
    max_size=10,
    timeout=10,
    open=True,
    kwargs={"row_factory": dict_row},
)

# Close cleanly so interpreter shutdown does not try to join pool threads.
atexit.register(pool.close)
