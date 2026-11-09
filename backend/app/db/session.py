"""Session lifecycle (D1: separate sessions, short write transactions).

One session per web request (FastAPI dependency) and one per scanner tick.
Sessions are closed on exit; callers commit explicitly and promptly.
"""
from collections.abc import Iterator

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


class SessionFactory:
    """Binds one SQLAlchemy sessionmaker to an engine."""

    def __init__(self, engine: Engine):
        self._maker = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )

    def create(self) -> Session:
        """A fresh session (requests, scanner ticks, CLI tools)."""
        return self._maker()

    def get(self) -> Iterator[Session]:
        """FastAPI dependency: one session per request, always closed."""
        session = self.create()
        try:
            yield session
        finally:
            session.close()
