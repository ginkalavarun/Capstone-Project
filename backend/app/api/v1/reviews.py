"""Customer review endpoint (batch 6: REV-01…05, D31).

    POST /api/v1/orders/{id}/review   the purchasing customer, only for
                                      actually delivered orders (D31),
                                      one review per order (REV-02/03)

(The optional public per-dish review listing, REV-04, is not implemented
in this batch — it is an optional enhancement, not an assignment
requirement.)
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.config import Settings
from ...core.deps import build_get_current_user
from ...db.models import User
from ...db.session import SessionFactory
from ...schemas.refunds import ReviewIn, ReviewOut
from ...services.reviews import create_review


def build_reviews_router(session_factory: SessionFactory, settings: Settings) -> APIRouter:
    router = APIRouter()
    get_current_user = build_get_current_user(session_factory, settings)
    Db = Annotated[Session, Depends(session_factory.get)]
    UserDep = Annotated[User, Depends(get_current_user)]

    @router.post(
        "/orders/{order_id}/review",
        status_code=201,
        response_model=ReviewOut,
        responses={
            409: {"description": "ORDER_INELIGIBLE (not delivered) or REVIEW_EXISTS (one per order)"},
        },
    )
    def review(order_id: int, payload: ReviewIn, user: UserDep, db: Db):
        """Rate an order after it was actually delivered (REV-01)."""
        created = create_review(db, user, order_id, payload.rating, payload.comment)
        return ReviewOut.model_validate(created)

    return router
