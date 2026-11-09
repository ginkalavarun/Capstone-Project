"""Owner dashboard response shapes (batch 6: DASH-02 stats; batch 7: reminders).

Every monetary value is integer cents of the single application currency
(D3, D26). The metrics are deliberately named for what they measure — the
gross mock-paid amount is *not* blindly called "revenue" (D35).

| Metric                  | Definition |
|---|---|
| `orders_by_status`      | counts of the restaurant's orders (placed in the range) by **current** status; all nine statuses always present |
| `gross_mock_paid_cents` | Σ `total_cents` over orders placed in the range — every placed order produced exactly one `mock_paid` ledger event |
| `refunded_cents`        | Σ `refunded` ledger events in the range (cancellation reversals **and** approved refunds, D29/D30) |
| `net_retained_cents`    | `gross_mock_paid_cents − refunded_cents` |
| `delivered_count`       | orders actually delivered in the range (`delivered_at` in range) — **including** later-refunded ones (D31) |
| `items_sold`            | Σ order-item quantities for the range's orders (D19) |
| `avg_order_value_cents` | `gross_mock_paid_cents ÷ placed_order_count` (integer floor) |
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class OwnerStatsOut(BaseModel):
    currency: str
    date_from: Optional[datetime]
    date_to: Optional[datetime]
    placed_order_count: int
    orders_by_status: dict[str, int]
    gross_mock_paid_cents: int
    refunded_cents: int
    net_retained_cents: int
    delivered_count: int
    items_sold: int
    avg_order_value_cents: int


class ReminderOut(BaseModel):
    """An open reminder with the order context an owner needs to act on
    (BG-04: owner of the restaurant only; the customer's identity is not
    exposed beyond the order's own fields)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    status_at_reminder: str  # PLACED | ACCEPTED — the episode's status
    detected_at: datetime
    resolved: bool
    resolved_at: Optional[datetime]
    order_status: str  # the order's *current* status (may have progressed)
    order_total_cents: int
    order_created_at: datetime
