"""Customer reviews (batch 6: REV-01…05, D31).

Eligibility is the **`delivered_at` timestamp**, not the current order
status (D31): an order that was delivered and later refunded remains
reviewable, because the customer really did receive the food. A
cancelled/pre-delivery order (no `delivered_at`) is never reviewable.

One review per order (REV-02): checked in the service and backstopped by
the database (`uq_reviews_order`, T-M9-10 proves the constraint).
No edit or delete path exists in this batch (approved scope, D31).
"""
from typing import Optional

from ..core import constants as C
from ..core.errors import ApiError
from ..db.models import Order, Review, User
from sqlalchemy.orm import Session
from . import transitions as T  # shared guards (D7 module)


def create_review(
    db: Session, user: User, order_id: int, rating: int, comment: Optional[str]
) -> Review:
    T._require_role(user, C.ROLE_CUSTOMER)
    order = T._load_order(db, order_id)
    T._require_customer(user, order)
    if order.delivered_at is None:
        raise ApiError(
            409, "ORDER_INELIGIBLE",
            "Reviews are possible only for actually delivered orders.",
        )
    if order.review is not None:
        raise ApiError(
            409, "REVIEW_EXISTS",
            "This order already has a review (one per order — REV-02/03).",
        )
    review = Review(
        order_id=order.id,
        customer_id=user.id,  # the purchasing customer, from the token (D8)
        rating=rating,
        comment=comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review
