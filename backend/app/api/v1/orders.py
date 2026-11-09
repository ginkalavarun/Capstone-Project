"""Order endpoints (batch 4: checkout + customer views).

    POST /api/v1/orders          place a mock-paid order (CK-01…10, D34)
    GET  /api/v1/orders          own history: status + date filters (ORDR-01)
    GET  /api/v1/orders/{id}     detail — customer / owning owner / assigned
                                  partner (ORDR-02, D8)

Lifecycle mutations live in `lifecycle.py` (batch 5); refunds, reviews, and
owner stats in `refunds.py` / `reviews.py` / `owner.py` (batch 6).
"""
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ...core import constants as C
from ...core.config import Settings
from ...core.deps import build_get_current_user
from ...core.errors import ApiError
from ...db.models import Order, User
from ...db.session import SessionFactory
from ...schemas.orders import CheckoutIn, OrderOut
from ...schemas.pagination import Page, PaginationParams
from ...services.checkout import place_order


def build_orders_router(session_factory: SessionFactory, settings: Settings) -> APIRouter:
    router = APIRouter()
    get_current_user = build_get_current_user(session_factory, settings)
    Db = Annotated[Session, Depends(session_factory.get)]
    UserDep = Annotated[User, Depends(get_current_user)]
    PageDep = Annotated[PaginationParams, Depends()]

    @router.post("/orders", status_code=201, response_model=OrderOut,
                 responses={200: {"description": "Idempotent retry of an existing order (D34)"}})
    def create_order(payload: CheckoutIn, user: UserDep, db: Db):
        """Checkout. 201 when a new order is created; 200 with the *original*
        order when an identical request is retried (D34)."""
        order, created = place_order(db, user, payload)
        return Response(
            status_code=201 if created else 200,
            content=OrderOut.from_order(order).model_dump_json(),
            media_type="application/json",
        )

    @router.get("/orders", response_model=Page[OrderOut])
    def list_own_orders(
        page: PageDep,
        user: UserDep,
        db: Db,
        status: Annotated[Optional[str], Query(max_length=20)] = None,
        date_from: Annotated[Optional[datetime], Query(description="created_at >= (ISO-8601)")] = None,
        date_to: Annotated[Optional[datetime], Query(description="created_at <= (ISO-8601)")] = None,
    ) -> Page[OrderOut]:
        """ORDR-01: the caller's own orders, filter by status + date, paginated.

        Customers can only ever see their own orders (AUTHZ-02) — a foreign
        id on the detail route is a 404, not a 403.
        """
        if user.role != C.ROLE_CUSTOMER:
            raise ApiError(403, "ROLE_FORBIDDEN", "Only customers list their own orders here.")
        query = db.query(Order).filter(Order.customer_id == user.id)
        if status is not None:
            if status not in C.ORDER_STATUSES:
                raise ApiError(422, "VALIDATION_ERROR",
                               f"Unknown status filter: {status}.")
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

    @router.get("/orders/{order_id}", response_model=OrderOut)
    def get_order(order_id: int, user: UserDep, db: Db) -> OrderOut:
        """ORDR-02 detail: the order's customer, the owner of its restaurant,
        or its assigned partner may read it. Otherwise 404 (AUTHZ-06)."""
        order = db.get(Order, order_id)
        if order is None:
            raise ApiError(404, "NOT_FOUND", "Order not found.")
        if user.role == C.ROLE_CUSTOMER:
            if order.customer_id != user.id:
                raise ApiError(404, "NOT_FOUND", "Order not found.")
        elif user.role == C.ROLE_OWNER:
            if order.restaurant is None or order.restaurant.owner_id != user.id:
                raise ApiError(404, "NOT_FOUND", "Order not found.")
        elif user.role == C.ROLE_PARTNER:
            if order.delivery_partner_id != user.id:
                raise ApiError(404, "NOT_FOUND", "Order not found.")
        else:  # defensive: roles are constrained by the database
            raise ApiError(403, "ROLE_FORBIDDEN", "Role not allowed.")
        return OrderOut.from_order(order)

    return router
