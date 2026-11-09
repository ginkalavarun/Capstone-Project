"""FastAPI application factory.

Wiring:
- configuration with the D4 startup guard (safe JWT secret required),
- explicit CORS allowlist (D10),
- the `{"detail", "code"}` error format (D14),
- request-logging middleware (MW-01/02/03; batch 1),
- Alembic migrations applied before the app serves traffic (D11 — safe in
  the documented single-worker configuration),
- the reminder scanner (D6; batch 7) started/stopped in the lifespan,
- the `/api/v1` router (feature routers land per batch).

The OpenAI key is optional here (D9: the insights feature degrades cleanly);
the JWT secret is not.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1 import build_api_router
from .core.config import Settings, get_settings
from .core.errors import register_error_handlers
from .db.engine import make_engine
from .db.migrate import run_migrations
from .db.session import SessionFactory
from .middleware.request_logging import RequestLoggingMiddleware
from .services.reminders import ReminderScanner

logger = logging.getLogger("campusbite")


def create_app(
    settings: Optional[Settings] = None,
    openai_client_factory: Optional[Callable[[], object]] = None,
) -> FastAPI:
    """Application factory.

    ``openai_client_factory`` is a test seam only (D9): production passes
    None and the real OpenAI client is built lazily from the environment
    key; tests inject a fake so the suite never touches the network.
    """
    settings = settings or get_settings()

    engine = make_engine(settings.database_url, enable_wal=settings.enable_sqlite_wal)
    session_factory = SessionFactory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.run_migrations_on_startup:
            run_migrations(settings.database_url)
        # The reminder scanner (D6, batch 7): a managed periodic thread,
        # 60 s in production. Gated by config so tests stay hermetic;
        # stopped (and joined) on shutdown for a clean exit.
        scanner: Optional[ReminderScanner] = None
        if settings.reminder_scanner_enabled:
            scanner = ReminderScanner(
                session_factory,
                interval_seconds=settings.reminder_interval_seconds,
                stale_minutes=settings.reminder_stale_minutes,
            )
            scanner.start()
            logger.info(
                "reminder scanner started (interval=%ss, stale=%smin, single-worker)",
                settings.reminder_interval_seconds,
                settings.reminder_stale_minutes,
            )
        app.state.reminder_scanner = scanner
        try:
            yield
        finally:
            if scanner is not None:
                scanner.stop()
                logger.info("reminder scanner stopped")

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        # Docs live under the API prefix so /api/v1 is the single namespace
        # (test-plan T-M2-02: GET /api/v1/docs, /api/v1/openapi.json).
        # `openapi_prefix` is deliberately NOT set: operation paths already
        # include the router prefix, and the UI would otherwise double it.
        docs_url=f"{settings.api_base_path}/docs",
        openapi_url=f"{settings.api_base_path}/openapi.json",
        redoc_url=f"{settings.api_base_path}/redoc",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    register_error_handlers(app)

    app.include_router(
        build_api_router(session_factory, settings, openai_client_factory),
        prefix=settings.api_base_path,
    )
    return app


# `uvicorn app.main:app` entry point. Importing this module with an unsafe
# JWT_SECRET raises ConfigError — the documented fail-fast behavior (D4).
app = create_app()
