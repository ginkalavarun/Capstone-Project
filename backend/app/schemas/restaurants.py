"""Restaurant & menu schemas (batch 3; RST-01…03, MENU-01…06).

Money convention (D3/D26): every ``*_cents`` field is an integer number of
euro cents. Timestamps are aware UTC (D33) and serialize as ISO-8601 with a
``+00:00`` offset.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Sanity cap on a dish price: €100,000. Above this is almost certainly a
#: bug (a missing decimal point) and is rejected with 422 (contract §money).
PRICE_MAX_CENTS = 10_000_000


class RestaurantOut(BaseModel):
    """Public catalog view. No user/owner PII beyond what a listing needs."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str]
    address: str
    delivery_fee_cents: int  # EUR (D26)
    created_at: datetime
    updated_at: datetime


class MenuItemOut(BaseModel):
    """One dish. `available=false` means soft-removed (RST-03/D32): still
    readable in the public catalog, excluded from checkout (MENU-07, M6)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurant_id: int
    name: str
    description: Optional[str]
    price_cents: int  # EUR (D26)
    available: bool
    created_at: datetime
    updated_at: datetime


class CreateMenuItemIn(BaseModel):
    """Owner adds a dish (MENU-03). `extra="forbid"`: unknown fields → 422,
    and a client can never smuggle in e.g. `restaurant_id` or `id`."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    price_cents: int = Field(ge=0, le=PRICE_MAX_CENTS)
    available: bool = True

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        # `min_length` alone would accept "   " — reject whitespace-only names.
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()


class UpdateMenuItemIn(BaseModel):
    """Owner updates a dish (MENU-04) or toggles availability (MENU-05).

    Partial update: only the fields present in the body change.
    For `description`, `null` means "keep the current value" and `""`
    means "clear it" (pydantic cannot express the difference otherwise).
    """

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    price_cents: Optional[int] = Field(default=None, ge=0, le=PRICE_MAX_CENTS)
    available: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None  # absent field = keep current name
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()
