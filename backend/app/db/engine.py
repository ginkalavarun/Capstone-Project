"""Engine factory with the SQLite safety rails (D1, D33).

- **Foreign keys are a per-connection pragma in SQLite** (off by default):
  a `connect` event listener enables `PRAGMA foreign_keys = ON` on *every*
  new connection. This is the main "silent failure" trap — a listener, not a
  one-time setup step (T-M3-03/13 prove it).
- `check_same_thread=False` lets the documented single-worker background
  scanner use its own sessions from another thread; `timeout=10` makes a
  queued writer wait briefly instead of failing under SQLite's single-writer
  model.
- **Timestamps (D33):** the application generates every timestamp as an
  aware-UTC datetime; SQLite stores it as ISO-8601 text
  (`YYYY-MM-DD HH:MM:SS.ffffff +00:00`). The database never creates time.
"""
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine


def utcnow() -> datetime:
    """The app's single source of 'now': aware UTC (D33)."""
    return datetime.now(timezone.utc)


def make_engine(database_url: str, *, enable_wal: bool = False) -> Engine:
    is_sqlite = database_url.startswith("sqlite")
    connect_args: dict = {}
    if is_sqlite:
        connect_args = {"check_same_thread": False, "timeout": 10}
    engine = create_engine(
        database_url, connect_args=connect_args, pool_pre_ping=True
    )
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _sqlite_safety(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            if enable_wal:
                cursor.execute("PRAGMA journal_mode = WAL")
            cursor.close()
    return engine
