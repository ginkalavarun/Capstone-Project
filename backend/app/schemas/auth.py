"""Auth request/response schemas (batch 2).

Monetary/timestamp conventions for later schemas live in
`app/schemas/money.py` when they land; keep schemas free of business logic
(validation only — authorization happens in deps/routers).
"""
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..db.models import User


class RegisterIn(BaseModel):
    """Public registration: creates a *customer* only (D2).

    `extra="forbid"` is deliberate (T-M4-02): any extra field — in
    particular an attempted `"role": "restaurant_owner"` — is rejected with
    422 instead of being silently ignored.
    """

    model_config = ConfigDict(extra="forbid")

    email: EmailStr  # normalized to lowercase by the validator
    # Kept permissive here; the *byte-based* policy (8–72, D4) is enforced
    # in the service via `validate_password` so multi-byte characters are
    # counted in bytes, never truncated.
    password: str = Field(min_length=1, max_length=512)
    full_name: str = Field(min_length=1, max_length=120)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=512)


class UserOut(BaseModel):
    """The profile the API exposes: never the password hash (D4)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
        )


class RegisterOut(BaseModel):
    user: UserOut


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
