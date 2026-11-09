"""Refund-request lifecycle (batch 6: REF-01…06, D28/D30).

Three operations, each following the documented authorization order:
role (403) → ownership (404, existence hidden — AUTHZ-06) → state check
(409 / 404). The shared guards are imported from the state machine module
(`transitions`) so both features can never drift apart.

**D28 — one refund request per order, permanently.** The request row is
never deleted and never replaced: a rejected request still blocks a
second one, and there is no "re-request" flow. The database backstop is
`uq_refunds_order` (at most one row per order).

**D30 — approval is atomic and the only path to `REFUNDED` after
delivery.** One transaction performs: the central machine's `refund` edge
(DELIVERED → REFUNDED, compare-and-swap), payment → `refunded`, the
request → `approved`, and **exactly one** `refunded` ledger row for the
full `total_cents` (D27). Double-approval is a 200 no-op (REF-04); the
ledger's `uq(order_id, type)` is the last-line backstop against a second
`refunded` event.

**Concurrency** (documented single-worker SQLite: a transaction holds the
write lock until it commits, so a competitor re-evaluates after the
winner commits):
- `approve`: CAS the order, then a *conditional* request update
  (`WHERE status = 'pending'`). If that matches 0 rows a concurrent
  rejection won the request — the whole transaction rolls back (the CAS
  included) and the caller gets 409. The order is never left REFUNDED
  with a non-approved request.
- `reject`: a *conditional* request update only; 0 rows → 409. It writes
  nothing on the order (REF-05).
"""
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..core import constants as C
from ..core.errors import ApiError
from ..db.engine import utcnow
from ..db.models import Order, PaymentLedger, RefundRequest, User
from . import transitions as T  # shared guards + the `refund` edge (D7)


def _request(db: Session, order: Order) -> Optional[RefundRequest]:
    return order.refund_request


def _decided_error() -> ApiError:
    return ApiError(
        409, "REFUND_ALREADY_DECIDED",
        "This refund request was already decided.",
    )


def request_refund(db: Session, user: User, order_id: int, reason: str) -> RefundRequest:
    """The purchasing customer requests a refund (REF-01/02, D28).

    Allowed only while the order is DELIVERED, and only once — the
    existing-request check comes first so a rejected (or approved)
    request still answers 409, permanently.
    """
    T._require_role(user, C.ROLE_CUSTOMER)
    order = T._load_order(db, order_id)
    T._require_customer(user, order)
    if _request(db, order) is not None:
        raise ApiError(
            409, "REFUND_REQUEST_EXISTS",
            "This order already has a refund request (one per order, "
            "permanently — D28).",
        )
    if order.status != C.ORDER_DELIVERED:
        raise ApiError(
            409, "ORDER_INELIGIBLE",
            f"Refund requests are possible only for DELIVERED orders (currently {order.status}).",
        )
    request = RefundRequest(order_id=order.id, status=C.REFUND_PENDING, reason=reason)
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


def approve_refund(db: Session, user: User, order_id: int) -> Order:
    """The restaurant owner approves the pending request (REF-03/04, D30).

    Idempotent: approving an already-approved request returns the current
    state (200) and writes nothing — it can never create a second refund
    ledger row, even under a race.
    """
    T._require_role(user, C.ROLE_OWNER)
    order = T._load_order(db, order_id)
    T._require_order_owner(user, order)
    request = _request(db, order)
    if request is None:
        raise ApiError(404, "NOT_FOUND", "No refund request for this order.")
    if request.status == C.REFUND_APPROVED:
        return order  # no-op (REF-04): the refund happened exactly once
    if request.status == C.REFUND_REJECTED:
        raise _decided_error()
    # pending → apply the central machine's refund edge, atomically with
    # the payment flip.
    if not T._cas(db, order, "refund", extra={"payment_status": C.PAYMENT_REFUNDED}):
        db.refresh(order)
        if order.status == C.ORDER_REFUNDED:
            return order  # a concurrent approval won — idempotent no-op
        raise ApiError(
            409, "ORDER_INELIGIBLE",
            f"Refund approval requires a DELIVERED order (currently {order.status}).",
        )
    # Conditional request update: if a concurrent rejection changed the
    # request under us, roll *everything* back (CAS included) rather than
    # leaving a REFUNDED order with a rejected/pending request.
    result = db.execute(
        update(RefundRequest)
        .where(RefundRequest.id == request.id, RefundRequest.status == C.REFUND_PENDING)
        .values(status=C.REFUND_APPROVED, decided_at=utcnow(), decided_by=user.id)
    )
    if result.rowcount != 1:
        db.rollback()
        raise _decided_error()
    db.add(PaymentLedger(
        order_id=order.id,
        type=C.PAYMENT_REFUNDED,
        amount_cents=order.total_cents,  # full refund incl. fee (D27)
    ))
    db.commit()
    return T._fresh_order(db, order.id)


def reject_refund(db: Session, user: User, order_id: int) -> Order:
    """The restaurant owner rejects the request (REF-05, D28).

    The request becomes `rejected`; the order and payment are untouched
    (it stays DELIVERED / mock_paid). Deciding twice is a 409, and a
    rejected request stays rejected — the customer cannot re-request
    (D28), so the order remains refund-eligible in practice only through
    the original request's single decision.
    """
    T._require_role(user, C.ROLE_OWNER)
    order = T._load_order(db, order_id)
    T._require_order_owner(user, order)
    request = _request(db, order)
    if request is None:
        raise ApiError(404, "NOT_FOUND", "No refund request for this order.")
    if request.status != C.REFUND_PENDING:
        raise _decided_error()
    result = db.execute(
        update(RefundRequest)
        .where(RefundRequest.id == request.id, RefundRequest.status == C.REFUND_PENDING)
        .values(status=C.REFUND_REJECTED, decided_at=utcnow(), decided_by=user.id)
    )
    if result.rowcount != 1:
        db.rollback()
        raise _decided_error()
    db.commit()
    db.refresh(request)
    return order  # unchanged — REF-05
