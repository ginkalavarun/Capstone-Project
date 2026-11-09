"""Refund request/decision endpoints (batch 6: REF-01…06, D28/D30).

    POST /api/v1/orders/{id}/refund-request   customer — own DELIVERED order,
                                              one request permanently
    POST /api/v1/orders/{id}/refund/approve   owner of the order's restaurant
    POST /api/v1/orders/{id}/refund/reject    owner of the order's restaurant

All three go through `services.refunds`; the business rules (and the
error codes `REFUND_REQUEST_EXISTS`, `ORDER_INELIGIBLE`,
`REFUND_ALREADY_DECIDED`) live there, not in the routes.
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.config import Settings
from ...core.deps import build_get_current_user
from ...db.models import User
from ...db.session import SessionFactory
from ...schemas.orders import OrderOut
from ...schemas.refunds import RefundRequestIn, RefundRequestOut
from ...services.refunds import approve_refund, reject_refund, request_refund


def build_refunds_router(session_factory: SessionFactory, settings: Settings) -> APIRouter:
    router = APIRouter()
    get_current_user = build_get_current_user(session_factory, settings)
    Db = Annotated[Session, Depends(session_factory.get)]
    UserDep = Annotated[User, Depends(get_current_user)]

    @router.post(
        "/orders/{order_id}/refund-request",
        status_code=201,
        response_model=RefundRequestOut,
        responses={
            409: {"description": "ORDER_INELIGIBLE (not DELIVERED) or REFUND_REQUEST_EXISTS (D28)"},
        },
    )
    def refund_request(order_id: int, payload: RefundRequestIn, user: UserDep, db: Db):
        """The purchasing customer requests a refund with a reason (REF-01)."""
        request = request_refund(db, user, order_id, payload.reason)
        return RefundRequestOut.model_validate(request)

    @router.post("/orders/{order_id}/refund/approve", response_model=OrderOut)
    def refund_approve(order_id: int, user: UserDep, db: Db):
        """Owner approves: order REFUNDED + payment refunded + exactly one
        `refunded` ledger row, atomically (D30). Approving an
        already-approved request is a 200 no-op (REF-04)."""
        return OrderOut.from_order(approve_refund(db, user, order_id))

    @router.post("/orders/{order_id}/refund/reject", response_model=OrderOut)
    def refund_reject(order_id: int, user: UserDep, db: Db):
        """Owner rejects: request `rejected`; order/payment untouched
        (REF-05). Deciding twice is a 409 (REF-02/D28)."""
        return OrderOut.from_order(reject_refund(db, user, order_id))

    return router
