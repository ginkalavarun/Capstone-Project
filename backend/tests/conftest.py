"""Shared fixtures for the CampusBite backend test suite.

Hermeticity rules (important — read before adding fixtures):

1. A **safe, non-placeholder** ``JWT_SECRET`` is set in the environment
   *before* any ``app`` import. ``app.main`` builds a module-level app on
   import, and the configuration guard (D4) refuses known placeholder
   secrets, so this must happen first.
2. The ``settings`` fixture constructs ``Settings(_env_file=None, ...)``
   with **every** field passed explicitly. pydantic-settings precedence is
   init-args > env vars > ``.env`` file, so a developer's local ``.env``
   can never leak real values into a test.
3. Every test runs against a throwaway SQLite file under pytest's
   ``tmp_path`` (docs/test-plan.md convention: isolated temporary DBs).
"""
import logging
import os

# --- Must run before the first `app` import (D4 startup guard). ---
UNIT_TEST_JWT_SECRET = "unit-test-secret-not-a-placeholder-1234567890"
os.environ.setdefault("JWT_SECRET", UNIT_TEST_JWT_SECRET)

# Keep pytest output readable: `run_migrations` configures the `alembic`
# logger to INFO via alembic.ini (good for operators); the migration
# progress lines are noise in test output. The child logger is not touched
# by fileConfig, so this stays in effect across repeated runs.
logging.getLogger("alembic.runtime.migration").setLevel(logging.WARNING)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.db.engine import make_engine  # noqa: E402
from app.db.migrate import run_migrations  # noqa: E402
from app.db.session import SessionFactory  # noqa: E402
from app.main import create_app  # noqa: E402


def make_test_settings(database_url: str, **overrides) -> Settings:
    """A fully explicit, hermetic ``Settings`` (see module docstring)."""
    values = dict(
        # app / api
        app_name="CampusBite API (tests)",
        api_base_path="/api/v1",
        # database (D1)
        database_url=database_url,
        run_migrations_on_startup=True,
        enable_sqlite_wal=False,
        # auth (D4)
        jwt_secret=UNIT_TEST_JWT_SECRET,
        jwt_algorithm="HS256",
        jwt_expire_minutes=60,
        password_min_bytes=8,
        password_max_bytes=72,
        # CORS (D10): exactly one allowlisted origin
        cors_origins="http://localhost:5173",
        # reminder scanner (D6): inert in batch 1; exercised with a
        # controlled clock in batch 7
        reminder_scanner_enabled=False,
        reminder_interval_seconds=60,
        reminder_stale_minutes=15,
        # AI (D9): no key in tests
        openai_api_key=None,
        openai_model="gpt-4o-mini",
        openai_timeout_seconds=30.0,
        ai_max_question_chars=500,
        ai_history_window=50,
        ai_rate_limit=10,
        ai_rate_window_minutes=10,
        # money (D3, D26)
        currency="EUR",
    )
    values.update(overrides)  # explicit per-test overrides win (e.g. jwt_secret)
    return Settings(_env_file=None, **values)


@pytest.fixture()
def db_url(tmp_path) -> str:
    """A throwaway SQLite file for this test (absolute path, 3 slashes)."""
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture()
def settings(db_url) -> Settings:
    return make_test_settings(db_url)


@pytest.fixture()
def app(settings):
    return create_app(settings)


@pytest.fixture()
def client(app):
    """TestClient as a *context manager*: the lifespan runs, so
    migrations are applied to the throwaway DB before the first request."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_factory(db_url):
    """Engine + SessionFactory for a migrated throwaway DB (DB-layer tests)."""
    engine = make_engine(db_url)
    run_migrations(db_url)
    factory = SessionFactory(engine)
    yield factory
    engine.dispose()


@pytest.fixture()
def db_session(db_factory):
    session = db_factory.create()
    yield session
    session.close()
