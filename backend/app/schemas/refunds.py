"""Refund-request and review schemas (batch 6: REF-01…06, REV-01…05).

Both bodies are single-purpose with `extra="forbid"`: the server derives
the customer from the token, the order from the path, and every status
from the state machine — a client-supplied status/customer/amount is
rejected, not reinterpreted (D8).
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RefundRequestIn(BaseModel):
    """`POST /orders/{id}/refund-request`.

    Exactly one field. D28: a second request — for any reason, even after
    the owner rejected the first — is a 409, so the body carries no
    "replace" or "force" semantics.
    """

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must not be blank.")
        return v


class RefundRequestOut(BaseModel):
    """The request as seen by its owner. `decided_by` is omitted: the
    customer does not need to know who decided (it is the restaurant's
    owner, by construction)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    status: str  # pending | approved | rejected
    reason: str
    requested_at: datetime
    decided_at: Optional[datetime]


class ReviewIn(BaseModel):
    """`POST /orders/{id}/review`: a 1–5 rating plus an optional bounded
    comment. One review per order (REV-02/03); no edit/delete path exists
    in this batch (D31 decision: eligibility only)."""

    model_config = ConfigDict(extra="forbid")

    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=1000)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    rating: int
    comment: Optional[str]
    created_at: datetime
