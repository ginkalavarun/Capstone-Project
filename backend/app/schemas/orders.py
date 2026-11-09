"""Order & checkout schemas (batch 4; CK-01…10, ORDR-01/02).

Money/timestamp conventions: integer EUR cents, aware-UTC ISO-8601 (D3, D26,
D33) — see docs/api-contract.md §conventions.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


#: Cart-line sanity cap (contract §money): one line of 100 is a bug, not a
#: dinner. Larger is rejected with 422 rather than silently accepted.
MAX_QTY = 100


class CheckoutItemIn(BaseModel):
    """One cart line. Only the id and quantity are trusted inputs; any extra
    fields (client-side names, prices, line totals) are ignored (CK-02,
    T-M6-02) — the server snapshots the truth from the database."""

    model_config = ConfigDict(extra="ignore")

    menu_item_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=MAX_QTY)


class CheckoutIn(BaseModel):
    """`POST /orders` body.

    `extra="ignore"` is deliberate (T-M6-02): a tampered or stale client field
    — `total_cents`, a `status`, a `customer_id` — is *ignored*, never fatal.
    The server recomputes every price/total from the database (D3); failing a
    retry because an old client build added a field would break the idempotent
    retry contract (D34).

    `idempotency_key` is a client-generated string, 1–64 chars (D34). It
    scopes to the authenticated customer: the *same* key with a *different*
    checkout payload is a client bug → 409 IDEMPOTENCY_MISMATCH.
    """

    model_config = ConfigDict(extra="ignore")

    items: list[CheckoutItemIn] = Field(min_length=1)
    delivery_address: str = Field(min_length=1, max_length=255)
    idempotency_key: str = Field(min_length=1, max_length=64)

    @field_validator("delivery_address")
    @classmethod
    def _address_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("delivery_address must not be blank")
        return v.strip()


class OrderItemOut(BaseModel):
    """A receipt line: the *snapshot* taken at order time (D3). Renamed or
    repriced menu items never change what this says."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    menu_item_id: int
    item_name: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int


class OrderOut(BaseModel):
    """The order shape shared by create/list/detail endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    payment_status: str
    refund_status: Optional[str]  # None | pending | approved | rejected (REF-06)
    refund_reason: Optional[str]  # the customer's request reason, when a
                                  # request exists (batch 8 — the owner
                                  # needs it to decide; None otherwise)
    status_updated_at: datetime
    delivered_at: Optional[datetime]
    restaurant_id: int
    restaurant_name: str
    customer_id: int
    customer_name: str  # DELV-02: the assigned partner needs a recipient
    delivery_partner_id: Optional[int]
    delivery_address: str
    items_subtotal_cents: int
    delivery_fee_cents: int
    total_cents: int
    items: list[OrderItemOut]
    created_at: datetime

    @classmethod
    def from_order(cls, order) -> "OrderOut":
        # Explicit construction: `restaurant_name` / `customer_name` are
        # derived from relationships and have no matching columns, so
        # `model_validate(order)` alone cannot supply them.
        return cls(
            id=order.id,
            status=order.status,
            payment_status=order.payment_status,
            refund_status=(
                order.refund_request.status
                if order.refund_request is not None
                else None
            ),
            refund_reason=(
                order.refund_request.reason
                if order.refund_request is not None
                else None
            ),
            status_updated_at=order.status_updated_at,
            delivered_at=order.delivered_at,
            restaurant_id=order.restaurant_id,
            restaurant_name=(
                order.restaurant.name if order.restaurant is not None else ""
            ),
            customer_id=order.customer_id,
            customer_name=(
                order.customer.full_name if order.customer is not None else ""
            ),
            delivery_partner_id=order.delivery_partner_id,
            delivery_address=order.delivery_address,
            items_subtotal_cents=order.items_subtotal_cents,
            delivery_fee_cents=order.delivery_fee_cents,
            total_cents=order.total_cents,
            items=[OrderItemOut.model_validate(i) for i in order.items],
            created_at=order.created_at,
        )


class AssignIn(BaseModel):
    """`POST /orders/{id}/assign`: exactly one field, and it must be an
    existing active partner (validated server-side; ORDER-06/D5)."""

    model_config = ConfigDict(extra="forbid")

    delivery_partner_id: int = Field(gt=0)


class StatusIn(BaseModel):
    """Target status for the prep / delivery-status endpoints. The target is
    range-checked in the service (ORDER-05/07); the *edge* is enforced by
    the central machine (D7)."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1, max_length=20)
