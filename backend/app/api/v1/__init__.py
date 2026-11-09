"""Versioned API router (D14: everything under /api/v1)."""
from typing import Callable, Optional

from fastapi import APIRouter

from ...core.config import Settings
from ...db.session import SessionFactory
from .auth import build_auth_router
from .health import build_health_router
from .insights import build_insights_router
from .lifecycle import build_lifecycle_router
from .orders import build_orders_router
from .owner import build_owner_router
from .refunds import build_refunds_router
from .restaurants import build_restaurants_router
from .reviews import build_reviews_router


def build_api_router(
    session_factory: SessionFactory,
    settings: Settings,
    openai_client_factory: Optional[Callable[[], object]] = None,
) -> APIRouter:
    api = APIRouter()
    api.include_router(build_health_router(session_factory))
    api.include_router(build_auth_router(session_factory, settings))
    api.include_router(build_restaurants_router(session_factory, settings))
    api.include_router(build_orders_router(session_factory, settings))
    api.include_router(build_lifecycle_router(session_factory, settings))
    api.include_router(build_refunds_router(session_factory, settings))
    api.include_router(build_reviews_router(session_factory, settings))
    api.include_router(build_owner_router(session_factory, settings))
    api.include_router(
        build_insights_router(session_factory, settings, openai_client_factory)
    )
    # Feature routers are added per batch:
    # restaurants/menu (batch 3 ✓), orders/checkout (batch 4 ✓),
    # owner/delivery lifecycle (batch 5 ✓), refunds/reviews/stats (batch 6 ✓),
    # owner reminders (batch 7 ✓), AI insights (M10 ✓ — batch 10).
    return api
