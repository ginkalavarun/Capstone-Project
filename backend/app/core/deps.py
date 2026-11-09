"""Per-request authentication and reusable authorization helpers (D8).

The three-check rule (AUTHZ-01):
1. **Authentication** — ``get_current_user``: a valid, unexpired HS256
   bearer token whose subject resolves to an *active* user row loaded from
   the database (the DB is the source of truth, D4 — the token itself
   carries no trusted claims).
2. **Role** — ``require_roles(*roles)``: the user's role must be allowed.
3. **Resource ownership / assignment** — provided per feature (later
   batches): a valid role *alone* never grants access to someone else's
   resource (AUTHZ-02…04). Ownership failures raise 404 (hide existence);
   role failures raise 403 (AUTHZ-06).

Nothing in this module logs tokens or passwords (D4/D23).
"""
from typing import Annotated, Callable

import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from . import constants as C
from .config import Settings
from .errors import ApiError
from ..db.models import MenuItem, User
from ..db.session import SessionFactory

# The `Bearer ` prefix is the only accepted scheme (assignment: JWT).
BEARER_PREFIX = "Bearer "


def build_get_current_user(session_factory: SessionFactory, settings: Settings):
    """Factory: returns the ``get_current_user`` FastAPI dependency.

    One session per request (``session_factory.get``) — the user row is
    read on every request, so deactivation takes effect immediately
    (AUTH-05, T-M4-07).
    """

    def get_current_user(request: Request, db: Session = Depends(session_factory.get)) -> User:
        header = request.headers.get("Authorization", "")
        if not header.startswith(BEARER_PREFIX):
            raise ApiError(401, "TOKEN_MISSING", "Authentication required: send a bearer token.")
        token = header[len(BEARER_PREFIX):].strip()
        if not token:
            raise ApiError(401, "TOKEN_MALFORMED", "Authentication required: send a bearer token.")
        try:
            claims = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],  # explicit allowlist: HS256 only
                options={"require": ["exp", "sub"]},
            )
        except jwt.ExpiredSignatureError:
            raise ApiError(401, "TOKEN_EXPIRED", "Token expired. Please log in again.")
        except jwt.PyJWTError:
            raise ApiError(401, "TOKEN_INVALID", "Invalid token.")
        if claims.get("type") != "access":
            raise ApiError(401, "TOKEN_INVALID", "Invalid token type.")
        try:
            user_id = int(claims["sub"])
        except (TypeError, ValueError):
            raise ApiError(401, "TOKEN_INVALID", "Invalid token subject.")
        user = db.get(User, user_id)
        if user is None:
            # The account no longer exists (or never did): uniform invalid.
            raise ApiError(401, "TOKEN_INVALID", "Invalid token.")
        if not user.is_active:
            raise ApiError(401, "USER_INACTIVE", "This account is deactivated.")
        return user

    return get_current_user


def build_require_roles(get_current_user: Callable, *allowed_roles: str) -> Callable:
    """Factory: dependency that authenticates, then enforces the role.

    Role failure → 403 (the caller is known but not permitted). Resource
    ownership is a *separate* later check in each feature (D8): this helper
    intentionally says nothing about whose resource is at stake.
    """

    def require_roles(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed_roles:
            raise ApiError(
                403,
                "ROLE_FORBIDDEN",
                f"This action requires one of: {', '.join(allowed_roles)}.",
            )
        return user

    return require_roles


def require_menu_item_owner(user: User, db: Session, menu_item_id: int) -> MenuItem:
    """Checks 2 + 3 (D8) for the flat `/menu-items/{id}` mutation endpoints.

    Order matters (authorization matrix): **role first** — a non-owner gets
    403 ROLE_FORBIDDEN; **ownership second** — an owner who does not own the
    item's restaurant gets 404 NOT_FOUND (never 403: that would reveal the
    item exists, AUTHZ-06). A valid role alone never grants access to
    someone else's menu (MENU-06, T-M5-09).
    """
    if user.role != C.ROLE_OWNER:
        raise ApiError(403, "ROLE_FORBIDDEN", "Only restaurant owners can manage menu items.")
    item = db.get(MenuItem, menu_item_id)
    if item is None or item.restaurant is None or item.restaurant.owner_id != user.id:
        raise ApiError(404, "NOT_FOUND", "Menu item not found.")
    return item


__all__ = [
    "BEARER_PREFIX",
    "build_get_current_user",
    "build_require_roles",
    "require_menu_item_owner",
]
