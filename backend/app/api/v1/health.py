"""Health endpoints (simple liveness + database readiness; never expose
configuration or credentials)."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...db.session import SessionFactory


def build_health_router(session_factory: SessionFactory) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @router.get("/health/db")
    def health_db(db: Session = Depends(session_factory.get)) -> dict:
        """Database readiness: reachable + FK pragma actually enabled (D1)."""
        db.execute(text("SELECT 1"))
        foreign_keys_enabled = bool(
            db.execute(text("PRAGMA foreign_keys")).scalar()
        )
        return {
            "status": "ok" if foreign_keys_enabled else "degraded",
            "database": "reachable",
            "foreign_keys_enabled": foreign_keys_enabled,
        }

    return router
