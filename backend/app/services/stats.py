"""Owner statistics (batch 6: DASH-02, the D35 metric set).

Owner-scoped by the caller's own restaurant (one restaurant per owner,
D24); the caller can never pass a restaurant id. All money is exact
integer-cent arithmetic (D3/D26) computed with SQL aggregates over the
caller's restaurant's rows.

Definitions (mirrored in docs/api-contract.md — D35):

- `orders_by_status`      — orders **placed** in the range, counted by
  current status; all nine statuses always present (zero-filled).
- `gross_mock_paid_cents` — Σ `total_cents` over the range's placed
  orders. Every placed order produced exactly one `mock_paid` ledger
  event at checkout, so this is the total value that was charged.
- `refunded_cents`        — Σ `refunded` ledger **events** in the range
  (cancellation reversals, D29, and approved refunds, D30).
- `net_retained_cents`    — `gross − refunded`, exactly.
- `delivered_count`       — orders with `delivered_at` in the range —
  **including** orders later refunded (D31).
- `items_sold`            — Σ order-item quantities of the range's orders.
- `avg_order_value_cents` — `gross ÷ placed_order_count` (integer floor;
  0 when nothing was placed in the range).

`date_from`/`date_to` bound an order's `created_at` for the order-based
metrics; the ledger-based metric (`refunded_cents`) and `delivered_count`
bound their own event/timestamp per the D35 definitions.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core import constants as C
from ..core.errors import ApiError
from ..db.models import Order, OrderItem, PaymentLedger, User
from ..schemas.stats import OwnerStatsOut
from . import transitions as T  # shared role guard


def _zeros(date_from: Optional[datetime], date_to: Optional[datetime]) -> OwnerStatsOut:
    return OwnerStatsOut(
        currency=C.CURRENCY,
        date_from=date_from,
        date_to=date_to,
        placed_order_count=0,
        orders_by_status={s: 0 for s in C.ORDER_STATUSES},
        gross_mock_paid_cents=0,
        refunded_cents=0,
        net_retained_cents=0,
        delivered_count=0,
        items_sold=0,
        avg_order_value_cents=0,
    )


def owner_stats(
    db: Session, user: User,
    date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
) -> OwnerStatsOut:
    T._require_role(user, C.ROLE_OWNER)
    restaurant = user.restaurant
    if restaurant is None:
        # Consistent with `GET /owner/orders` (batch 5): an owner without a
        # restaurant (should not exist — provisioning creates both
        # atomically) sees zeroed stats, not an error.
        return _zeros(date_from, date_to)

    # --- order-based metrics: the range bounds created_at ---------------
    orders = (
        db.query(Order).filter(Order.restaurant_id == restaurant.id)
    )
    if date_from is not None:
        orders = orders.filter(Order.created_at >= date_from)
    if date_to is not None:
        orders = orders.filter(Order.created_at <= date_to)

    placed_count = orders.count()
    gross = orders.with_entities(func.coalesce(func.sum(Order.total_cents), 0)).scalar()

    by_status = {s: 0 for s in C.ORDER_STATUSES}
    for status, count in (
        orders.with_entities(Order.status, func.count(Order.id)).group_by(Order.status).all()
    ):
        by_status[status] = count

    # --- ledger-based: refunded events in the range (event timestamp) ---
    refunded_q = (
        db.query(func.coalesce(func.sum(PaymentLedger.amount_cents), 0))
        .join(Order, PaymentLedger.order_id == Order.id)
        .filter(
            Order.restaurant_id == restaurant.id,
            PaymentLedger.type == C.PAYMENT_REFUNDED,
        )
    )
    if date_from is not None:
        refunded_q = refunded_q.filter(PaymentLedger.created_at >= date_from)
    if date_to is not None:
        refunded_q = refunded_q.filter(PaymentLedger.created_at <= date_to)
    refunded = refunded_q.scalar()

    # --- actually delivered in the range (incl. later-refunded, D31) ----
    delivered_q = db.query(func.count(Order.id)).filter(
        Order.restaurant_id == restaurant.id,
        Order.delivered_at.is_not(None),
    )
    if date_from is not None:
        delivered_q = delivered_q.filter(Order.delivered_at >= date_from)
    if date_to is not None:
        delivered_q = delivered_q.filter(Order.delivered_at <= date_to)
    delivered = delivered_q.scalar()

    # --- items sold (quantities of the range's order lines) -------------
    items_q = (
        db.query(func.coalesce(func.sum(OrderItem.quantity), 0))
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.restaurant_id == restaurant.id)
    )
    if date_from is not None:
        items_q = items_q.filter(Order.created_at >= date_from)
    if date_to is not None:
        items_q = items_q.filter(Order.created_at <= date_to)
    items_sold = items_q.scalar()

    avg = gross // placed_count if placed_count else 0
    return OwnerStatsOut(
        currency=C.CURRENCY,
        date_from=date_from,
        date_to=date_to,
        placed_order_count=placed_count,
        orders_by_status=by_status,
        gross_mock_paid_cents=gross,
        refunded_cents=refunded,
        net_retained_cents=gross - refunded,
        delivered_count=delivered,
        items_sold=items_sold,
        avg_order_value_cents=avg,
    )
