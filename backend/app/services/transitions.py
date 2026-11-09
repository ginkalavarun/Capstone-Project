"""The central order state machine (D7, ORDER-01) and named actions.

This is the **only** path by which `orders.status` changes. There is no
generic "set status" endpoint: every route maps to a named action with an
explicit (from, to) edge, an allowed actor, and an ownership condition
(docs/authorization-matrix.md, D8).

The edge table (brief §4 + D29/D30):

    action            from → to                actor
    cancel            PLACED → CANCELLED       the order's customer
    accept            PLACED → ACCEPTED        owner of the restaurant
    prep              ACCEPTED → PREPARING     owner of the restaurant
    ready             PREPARING → READY        owner of the restaurant
    assign            READY → ASSIGNED         owner of the restaurant
    out_for_delivery  ASSIGNED → OUT_FOR_DELIVERY   the assigned partner
    deliver           OUT_FOR_DELIVERY → DELIVERED  the assigned partner
    refund            DELIVERED → REFUNDED     owner of the restaurant
                                  (applied by the refund service, batch 6)

Concurrency (ORDER-08, §6 of docs/database.md): every action is a
*compare-and-swap* — `UPDATE … WHERE id = :id AND status = :from`. The
database arbitrates races: if the row no longer has the expected status
(someone beat us to it), the update touches 0 rows → `409
INVALID_TRANSITION`. A no-op re-POST of the current state is therefore a
409 that changes nothing — in particular it does **not** re-stamp
`status_updated_at` (ORDER-11: re-stamping would reset the reminder
clock, D6/D33).
"""
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..core import constants as C
from ..core.errors import ApiError
from ..db.engine import utcnow
from ..db.models import Order, User


class _Edge:
    __slots__ = ("from_status", "to_status")

    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status


#: action → the single edge it implements.
EDGES = {
    "cancel": _Edge(C.ORDER_PLACED, C.ORDER_CANCELLED),
    "accept": _Edge(C.ORDER_PLACED, C.ORDER_ACCEPTED),
    "prep": _Edge(C.ORDER_ACCEPTED, C.ORDER_PREPARING),
    "ready": _Edge(C.ORDER_PREPARING, C.ORDER_READY),
    "assign": _Edge(C.ORDER_READY, C.ORDER_ASSIGNED),
    "out_for_delivery": _Edge(C.ORDER_ASSIGNED, C.ORDER_OUT_FOR_DELIVERY),
    "deliver": _Edge(C.ORDER_OUT_FOR_DELIVERY, C.ORDER_DELIVERED),
    "refund": _Edge(C.ORDER_DELIVERED, C.ORDER_REFUNDED),  # batch 6 (D30)
}


def _cas(db: Session, order: Order, action: str, extra: dict | None = None) -> bool:
    """Apply the action's edge atomically. True iff the transition happened.

    `extra` holds related writes (e.g. `delivery_partner_id`, `delivered_at`)
    committed in the same transaction as the status change.
    """
    edge = EDGES[action]
    now = utcnow()
    values = {"status": edge.to_status, "status_updated_at": now, "updated_at": now}
    if extra:
        values.update(extra)
    result = db.execute(
        update(Order)
        .where(Order.id == order.id, Order.status == edge.from_status)
        .values(**values)
    )
    return result.rowcount == 1


def _require_role(user: User, role: str) -> None:
    if user.role != role:
        raise ApiError(403, "ROLE_FORBIDDEN", f"This action requires role: {role}.")


def _load_order(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise ApiError(404, "NOT_FOUND", "Order not found.")
    return order


def _fresh_order(db: Session, order_id: int) -> Order:
    """Post-commit re-read. The CAS is a Core UPDATE, which bypasses the
    ORM identity map; with `expire_on_commit=False` a plain `db.get` would
    return the *stale* in-memory values, so force a real re-SELECT."""
    order = db.get(Order, order_id)
    db.refresh(order)
    return order


def _require_order_owner(user: User, order: Order) -> None:
    if order.restaurant is None or order.restaurant.owner_id != user.id:
        raise ApiError(404, "NOT_FOUND", "Order not found.")


def _require_customer(user: User, order: Order) -> None:
    if order.customer_id != user.id:
        raise ApiError(404, "NOT_FOUND", "Order not found.")


def _require_assigned_partner(user: User, order: Order) -> None:
    if order.delivery_partner_id != user.id:
        raise ApiError(404, "NOT_FOUND", "Order not found.")


def _invalid_transition(action: str, current: str) -> ApiError:
    return ApiError(
        409,
        "INVALID_TRANSITION",
        f"Cannot {action} an order that is {current}.",
    )


# ---------------------------------------------------------------------------
# Named actions — each = authz pre-checks (role → ownership) + CAS + commit
# ---------------------------------------------------------------------------

def cancel_order(db: Session, user: User, order_id: int) -> Order:
    """Customer cancels *their* order (ORDER-02/03: only from PLACED).

    D29: cancellation is a **mock payment reversal**, not a refund request —
    order CANCELLED, payment `refunded`, exactly one `refunded` ledger row,
    all in this one transaction. No `refund_requests` row is created.
    """
    from ..db.models import PaymentLedger

    _require_role(user, C.ROLE_CUSTOMER)
    order = _load_order(db, order_id)
    _require_customer(user, order)
    if not _cas(db, order, "cancel", extra={"payment_status": C.PAYMENT_REFUNDED}):
        raise _invalid_transition("cancel", order.status)
    db.add(
        PaymentLedger(
            order_id=order.id,
            type=C.PAYMENT_REFUNDED,
            amount_cents=order.total_cents,  # full reversal incl. fee (D27)
        )
    )
    db.commit()
    return _fresh_order(db, order_id)


def accept_order(db: Session, user: User, order_id: int) -> Order:
    """Owner accepts a PLACED order (ORDER-04)."""
    _require_role(user, C.ROLE_OWNER)
    order = _load_order(db, order_id)
    _require_order_owner(user, order)
    if not _cas(db, order, "accept"):
        raise _invalid_transition("accept", order.status)
    db.commit()
    return _fresh_order(db, order_id)


def update_preparation(db: Session, user: User, order_id: int, target: str) -> Order:
    """Owner drives the prep chain (ORDER-05): ACCEPTED→PREPARING→READY.

    Target semantics (T-M7-06/T-M7-17):
    - not a known order status                   → 422 (bad input);
    - a known status outside PREPARING/READY     → 409 (the prep endpoint
      does not implement that target — the no-op re-POST family);
    - a valid target whose edge does not match   → 409 (CAS touches 0 rows).
    Every 409 path writes nothing, so `status_updated_at` is untouched
    (ORDER-11: re-stamping would reset the reminder clock, D6/D33).
    """
    _require_role(user, C.ROLE_OWNER)
    if target not in C.ORDER_STATUSES:
        raise ApiError(422, "VALIDATION_ERROR",
                       f"'{target}' is not a known order status.")
    order = _load_order(db, order_id)
    _require_order_owner(user, order)
    if target not in (C.ORDER_PREPARING, C.ORDER_READY):
        raise ApiError(409, "INVALID_TRANSITION",
                       f"Preparation updates accept PREPARING or READY, not {target}.")
    action = "prep" if target == C.ORDER_PREPARING else "ready"
    if not _cas(db, order, action):
        raise _invalid_transition(action, order.status)
    db.commit()
    return _fresh_order(db, order_id)


def assign_partner(db: Session, user: User, order_id: int, partner_id: int) -> Order:
    """Owner assigns an **active delivery partner** to a READY order
    (ORDER-06, D5): the partner's role and active status are validated, so a
    stale or forged id cannot poison the order.
    """
    from ..db.models import User as UserRow

    _require_role(user, C.ROLE_OWNER)
    order = _load_order(db, order_id)
    _require_order_owner(user, order)
    partner = db.get(UserRow, partner_id)
    if partner is None or partner.role != C.ROLE_PARTNER or not partner.is_active:
        raise ApiError(422, "VALIDATION_ERROR",
                       "Delivery partner not found or not active.")
    if not _cas(db, order, "assign", extra={"delivery_partner_id": partner.id}):
        raise _invalid_transition("assign", order.status)
    db.commit()
    return _fresh_order(db, order_id)


def update_delivery_status(db: Session, user: User, order_id: int, target: str) -> Order:
    """The **assigned** partner drives ASSIGNED→OUT_FOR_DELIVERY→DELIVERED
    (ORDER-07). Completing delivery stamps `delivered_at` (D31 — review
    eligibility survives a later refund).

    Target semantics mirror `update_preparation` (the T-M7-17 family):
    422 for unknown statuses, 409 for known ones this endpoint does not
    implement, 409 when the edge does not match the current state.
    """
    _require_role(user, C.ROLE_PARTNER)
    if target not in C.ORDER_STATUSES:
        raise ApiError(422, "VALIDATION_ERROR",
                       f"'{target}' is not a known order status.")
    order = _load_order(db, order_id)
    _require_assigned_partner(user, order)
    if target not in (C.ORDER_OUT_FOR_DELIVERY, C.ORDER_DELIVERED):
        raise ApiError(409, "INVALID_TRANSITION",
                       f"Delivery updates accept OUT_FOR_DELIVERY or DELIVERED, not {target}.")
    action = "out_for_delivery" if target == C.ORDER_OUT_FOR_DELIVERY else "deliver"
    extra = {"delivered_at": utcnow()} if action == "deliver" else None
    if not _cas(db, order, action, extra=extra):
        raise _invalid_transition(action, order.status)
    db.commit()
    return _fresh_order(db, order_id)
