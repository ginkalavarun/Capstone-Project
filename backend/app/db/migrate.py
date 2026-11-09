"""Migration runner (D11). Lives in the DB layer so tools like the seed
script can apply migrations without importing the (secret-guarded) app."""
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]  # .../backend


def run_migrations(database_url: str) -> None:
    """Apply all Alembic migrations to `database_url`.

    Safe in the documented single-worker setup (D1/D11); a manual
    `alembic upgrade head` is also documented for operators.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
