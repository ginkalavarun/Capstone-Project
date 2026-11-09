"""Order lifecycle & role dashboards (batch 5; ORDER-01…11, DELV-01…05).

    POST /api/v1/orders/{id}/cancel            customer (PLACED only, D29)
    POST /api/v1/orders/{id}/accept            owner (PLACED)
    POST /api/v1/orders/{id}/status            owner (prep chain: PREPARING/READY)
    POST /api/v1/orders/{id}/assign            owner (READY, active partner)
    POST /api/v1/orders/{id}/delivery-status   assigned partner (OFD/DELIVERED)
    GET  /api/v1/owner/orders                  owner (own restaurant, filtered)
    GET  /api/v1/delivery-partners             owner (active partners, id+name)
    GET  /api/v1/delivery/orders               partner (active assignments)
    GET  /api/v1/delivery/history              partner (past completed)
    GET  /api/v1/delivery/orders/{id}          partner (assigned to caller)

All mutations go through `services.transitions` — the central machine (D7).
Authorization order everywhere: role (403) → ownership/assignment (404)
→ edge (409 INVALID_TRANSITION) (authorization matrix, AUTHZ-06).
"""
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core import constants as C
from ...core.config import Settings
from ...core.deps import build_get_current_user
from ...core.errors import ApiError
from ...db.models import Order, User
from ...db.session import SessionFactory
from ...schemas.orders import AssignIn, OrderOut, StatusIn
from ...schemas.pagination import Page, PaginationParams
from ...services import transitions as T

#: "Done" states for the partner's split views (docs/api-contract.md §lifecycle).
DONE_STATUSES = (C.ORDER_DELIVERED, C.ORDER_REFUNDED)


def build_lifecycle_router(session_factory: SessionFactory, settings: Settings) -> APIRouter:
    router = APIRouter()
    get_current_user = build_get_current_user(session_factory, settings)
    Db = Annotated[Session, Depends(session_factory.get)]
    UserDep = Annotated[User, Depends(get_current_user)]
    PageDep = Annotated[PaginationParams, Depends()]

    # ------------------------------------------------------- order mutations

    @router.post("/orders/{order_id}/cancel", response_model=OrderOut)
    def cancel(order_id: int, user: UserDep, db: Db) -> OrderOut:
        """Customer cancels their own PLACED order (ORDER-02/03, D29):
        CANCELLED + payment `refunded` + one `refunded` ledger row, atomically.
        No `refund_requests` row (that is the post-delivery path, batch 6)."""
        order = T.cancel_order(db, user, order_id)
        return OrderOut.from_order(order)

    @router.post("/orders/{order_id}/accept", response_model=OrderOut)
    def accept(order_id: int, user: UserDep, db: Db) -> OrderOut:
        """Owner accepts a PLACED order (ORDER-04)."""
        return OrderOut.from_order(T.accept_order(db, user, order_id))

    @router.post("/orders/{order_id}/status", response_model=OrderOut)
    def prep_status(order_id: int, body: StatusIn, user: UserDep, db: Db) -> OrderOut:
        """Owner drives the prep chain (ORDER-05)."""
        return OrderOut.from_order(T.update_preparation(db, user, order_id, body.status))

    @router.post("/orders/{order_id}/assign", response_model=OrderOut)
    def assign(order_id: int, body: AssignIn, user: UserDep, db: Db) -> OrderOut:
        """Owner assigns an active delivery partner to a READY order
        (ORDER-06, D5)."""
        return OrderOut.from_order(T.assign_partner(db, user, order_id, body.delivery_partner_id))

    @router.post("/orders/{order_id}/delivery-status", response_model=OrderOut)
    def delivery_status(order_id: int, body: StatusIn, user: UserDep, db: Db) -> OrderOut:
        """The **assigned** partner updates delivery status (ORDER-07)."""
        return OrderOut.from_order(
            T.update_delivery_status(db, user, order_id, body.status)
        )

    # ------------------------------------------------------- owner dashboards

    @router.get("/owner/orders", response_model=Page[OrderOut])
    def owner_orders(
        page: PageDep,
        user: UserDep,
        db: Db,
        status: Annotated[Optional[str], Query(max_length=20)] = None,
        date_from: Annotated[Optional[datetime], Query()] = None,
        date_to: Annotated[Optional[datetime], Query()] = None,
    ) -> Page[OrderOut]:
        """DASH-01: incoming orders for the caller's restaurant (one per
        owner, D24), filter by status + date, paginated, newest first."""
        if user.role != C.ROLE_OWNER:
            raise ApiError(403, "ROLE_FORBIDDEN", "Owners only.")
        restaurant = user.restaurant
        if restaurant is None:
            return Page(items=[], total=0, limit=page.limit, offset=page.offset)
        query = db.query(Order).filter(Order.restaurant_id == restaurant.id)
        if status is not None:
            if status not in C.ORDER_STATUSES:
                raise ApiError(422, "VALIDATION_ERROR", f"Unknown status filter: {status}.")
            query = query.filter(Order.status == status)
        if date_from is not None:
            query = query.filter(Order.created_at >= date_from)
        if date_to is not None:
            query = query.filter(Order.created_at <= date_to)
        total = query.count()
        rows = (
            query.order_by(Order.created_at.desc(), Order.id.desc())
            .offset(page.offset)
            .limit(page.limit)
            .all()
        )
        return Page(
            items=[OrderOut.from_order(o) for o in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    @router.get("/delivery-partners", response_model=list[dict])
    def partner_listing(user: UserDep, db: Db) -> list[dict]:
        """DELV-04/D5: owners may assign from **active** partners only.
        Minimal response: id + display name — no emails or other PII."""
        if user.role != C.ROLE_OWNER:
            raise ApiError(403, "ROLE_FORBIDDEN", "Owners only.")
        partners = (
            db.query(User)
            .filter(User.role == C.ROLE_PARTNER, User.is_active.is_(True))
            .order_by(User.full_name, User.id)
            .all()
        )
        return [{"id": p.id, "full_name": p.full_name} for p in partners]

    # ------------------------------------------------------- partner dashboards

    def _partner_query(db: Db, user: User, *, done: bool):
        query = db.query(Order).filter(Order.delivery_partner_id == user.id)
        if done:
            query = query.filter(Order.status.in_(DONE_STATUSES))
        else:
            query = query.filter(~Order.status.in_(DONE_STATUSES))
        return query

    @router.get("/delivery/orders", response_model=Page[OrderOut])
    def partner_orders(
        page: PageDep,
        user: UserDep,
        db: Db,
        status: Annotated[Optional[str], Query(max_length=20)] = None,
    ) -> Page[OrderOut]:
        """DELV-01: orders **assigned to the caller** (never other partners'
        work — AUTHZ-04), active workload, filter by status, paginated."""
        if user.role != C.ROLE_PARTNER:
            raise ApiError(403, "ROLE_FORBIDDEN", "Delivery partners only.")
        query = _partner_query(db, user, done=False)
        if status is not None:
            if status not in C.ORDER_STATUSES:
                raise ApiError(422, "VALIDATION_ERROR", f"Unknown status filter: {status}.")
            query = query.filter(Order.status == status)
        total = query.count()
        rows = (
            query.order_by(Order.status_updated_at.desc(), Order.id.desc())
            .offset(page.offset)
            .limit(page.limit)
            .all()
        )
        return Page(
            items=[OrderOut.from_order(o) for o in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    @router.get("/delivery/history", response_model=Page[OrderOut])
    def partner_history(
        page: PageDep,
        user: UserDep,
        db: Db,
        status: Annotated[Optional[str], Query(max_length=20)] = None,
    ) -> Page[OrderOut]:
        """DELV-03: the caller's past completed assignments
        (DELIVERED, incl. later-REFUNDED)."""
        if user.role != C.ROLE_PARTNER:
            raise ApiError(403, "ROLE_FORBIDDEN", "Delivery partners only.")
        query = _partner_query(db, user, done=True)
        if status is not None:
            if status not in C.ORDER_STATUSES:
                raise ApiError(422, "VALIDATION_ERROR", f"Unknown status filter: {status}.")
            query = query.filter(Order.status == status)
        total = query.count()
        rows = (
            query.order_by(Order.delivered_at.desc().nullslast(), Order.id.desc())
            .offset(page.offset)
            .limit(page.limit)
            .all()
        )
        return Page(
            items=[OrderOut.from_order(o) for o in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    @router.get("/delivery/orders/{order_id}", response_model=OrderOut)
    def partner_order_detail(order_id: int, user: UserDep, db: Db) -> OrderOut:
        """DELV-02: the assigned partner sees the full order, incl. the
        customer's delivery details. Unassigned partners get 404."""
        if user.role != C.ROLE_PARTNER:
            raise ApiError(403, "ROLE_FORBIDDEN", "Delivery partners only.")
        order = db.get(Order, order_id)
        if order is None or order.delivery_partner_id != user.id:
            raise ApiError(404, "NOT_FOUND", "Order not found.")
        return OrderOut.from_order(order)

    return router
