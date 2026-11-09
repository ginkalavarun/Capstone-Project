"""Owner self-service endpoints.

    GET /api/v1/owner/restaurant batch 8 — the caller's own restaurant (the
                                 menu-management UI needs its id)
    GET /api/v1/owner/stats      batch 6 — DASH-02 stats, own restaurant only,
                                 the D35 metric set, optional date range
    GET /api/v1/owner/reminders  batch 7 — own restaurant only, the open
                                 stale-order reminders (BG-04, D6)
"""
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core import constants as C
from ...core.config import Settings
from ...core.deps import build_get_current_user
from ...core.errors import ApiError
from ...db.models import Order, ReminderLog, Restaurant, User
from ...db.session import SessionFactory
from ...schemas.pagination import Page, PaginationParams
from ...schemas.restaurants import RestaurantOut
from ...schemas.stats import OwnerStatsOut, ReminderOut
from ...services.stats import owner_stats


def _reminder_out(row: ReminderLog) -> ReminderOut:
    order = row.order
    return ReminderOut(
        id=row.id,
        order_id=row.order_id,
        status_at_reminder=row.status_at_reminder,
        detected_at=row.detected_at,
        resolved=row.resolved,
        resolved_at=row.resolved_at,
        order_status=order.status if order is not None else "?",
        order_total_cents=order.total_cents if order is not None else 0,
        # The INNER JOIN guarantees the order row (FK RESTRICT); the
        # fallback is defensive only.
        order_created_at=(
            order.created_at if order is not None else datetime.min.replace(tzinfo=timezone.utc)
        ),
    )


def build_owner_router(session_factory: SessionFactory, settings: Settings) -> APIRouter:
    router = APIRouter()
    get_current_user = build_get_current_user(session_factory, settings)
    Db = Annotated[Session, Depends(session_factory.get)]
    UserDep = Annotated[User, Depends(get_current_user)]
    PageDep = Annotated[PaginationParams, Depends()]

    @router.get("/owner/restaurant", response_model=RestaurantOut)
    def own_restaurant(user: UserDep) -> Restaurant:
        """Batch 8 (frontend enablement): the caller's own restaurant.

        The owner dashboard's menu-management page needs a restaurant id to
        call the menu endpoints with. One owner has at most one restaurant
        (D24), so there is nothing else to list. Non-owners → 403; an owner
        without a provisioned restaurant → 404.
        """
        if user.role != C.ROLE_OWNER:
            raise ApiError(403, "ROLE_FORBIDDEN", "Owners only.")
        if user.restaurant is None:
            raise ApiError(404, "NOT_FOUND", "No restaurant provisioned.")
        return user.restaurant

    @router.get("/owner/stats", response_model=OwnerStatsOut)
    def stats(
        user: UserDep,
        db: Db,
        date_from: Annotated[
            Optional[datetime], Query(description="created_at >= (ISO-8601)")] = None,
        date_to: Annotated[
            Optional[datetime], Query(description="created_at <= (ISO-8601)")] = None,
    ) -> OwnerStatsOut:
        """DASH-02: the D35 metric set for the caller's own restaurant.

        Owners can only ever see their own restaurant's numbers (D24); a
        restaurant id is not accepted, so there is no way to probe
        another restaurant.
        """
        return owner_stats(db, user, date_from, date_to)

    @router.get("/owner/reminders", response_model=Page[ReminderOut])
    def reminders(page: PageDep, user: UserDep, db: Db) -> Page[ReminderOut]:
        """BG-04/D6: the stale-order reminders for **this owner's**
        restaurant only — a different owner gets their own (empty) list,
        never foreign rows; non-owners get 403. Open reminders first,
        oldest detected first (a stale order is the one that needs action).
        """
        if user.role != C.ROLE_OWNER:
            raise ApiError(403, "ROLE_FORBIDDEN", "Owners only.")
        restaurant = user.restaurant
        if restaurant is None:
            return Page(items=[], total=0, limit=page.limit, offset=page.offset)
        query = (
            db.query(ReminderLog)
            .join(Order, ReminderLog.order_id == Order.id)
            .filter(Order.restaurant_id == restaurant.id)
            .filter(ReminderLog.resolved.is_(False))
        )
        total = query.count()
        rows = (
            query.order_by(ReminderLog.detected_at.asc(), ReminderLog.id.asc())
            .offset(page.offset)
            .limit(page.limit)
            .all()
        )
        return Page(
            items=[_reminder_out(r) for r in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    return router
