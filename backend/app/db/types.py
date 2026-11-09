"""Custom column types implementing the approved timestamp contract (D33).

SQLite's stock ``DATETIME`` in SQLAlchemy 2.0 stores
``YYYY-MM-DD HH:MM:SS.ffffff`` — the timezone is silently dropped on write
and reads come back as **naive** datetimes (verified empirically against
SQLAlchemy 2.0.36; the dialect's ``timezone=True`` flag is ignored by the
SQLite storage format).

docs/database.md §7 (approved, D33) requires the stored text to be
self-describing UTC::

    YYYY-MM-DD HH:MM:SS.ffffff +00:00

with reads returning **aware** UTC datetimes. ``UTCDateTime`` implements
exactly that on top of the SQLite ``DATETIME`` (text affinity; the emitted
DDL is identical to a plain ``DATETIME``, so the committed baseline
migration needs no change).

Rules:
- bind: aware → normalized to UTC, stored with a ``+00:00`` suffix;
  naive → interpreted as UTC (the application always generates aware
  values via ``utcnow()``; this also keeps any legacy row readable).
- result: text with an offset → parsed and normalized to UTC; text
  without an offset (legacy rows) → interpreted as UTC.
"""
from datetime import datetime, timezone

from sqlalchemy.dialects.sqlite import DATETIME as _SQLiteDATETIME

_STORAGE_FORMAT = "%Y-%m-%d %H:%M:%S.%f +00:00"


class UTCDateTime(_SQLiteDATETIME):
    """An aware-UTC ``DATETIME`` for SQLite (D33)."""

    def bind_processor(self, dialect):  # noqa: N802 (SQLAlchemy API)
        def process(value):
            if value is None:
                return None
            if not isinstance(value, datetime):
                return value
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            else:
                value = value.astimezone(timezone.utc)
            return value.strftime(_STORAGE_FORMAT)

        return process

    def result_processor(self, dialect, coltype):  # noqa: N802
        def process(value):
            if value is None or isinstance(value, datetime):
                return value
            if not isinstance(value, str):
                return value  # unexpected storage; let the caller surface it
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        return process
