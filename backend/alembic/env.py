"""Alembic environment: runs migrations against `DATABASE_URL` (D11).

The metadata is the ORM models' metadata, so autogenerate (used for future
schema changes) sees the source of truth. The database URL is read from the
DATABASE_URL environment variable (or the `sqlalchemy.url` main option, which
app.main::run_migrations sets explicitly).
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `app` importable regardless of the working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import models  # noqa: E402,F401  (registers all tables)
from app.db.base import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: this module also runs inside the app
    # process at startup (D11) and inside pytest; it must not silence the
    # application's or the test runner's existing loggers.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# DATABASE_URL wins over the (empty) main option; app.main sets the main
# option explicitly when it applies migrations at startup.
url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
if url:
    config.set_main_option("sqlalchemy.url", url)


def run_migrations_offline() -> None:
    """Offline mode: emit SQL to script stdout (no DB connection)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Online mode: connect and run migrations."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
