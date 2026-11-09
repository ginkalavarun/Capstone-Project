"""Restaurants & menu endpoints (batch 3).

Public catalog (D16 — no authentication):
    GET /restaurants                     paginated listing   (RST-01)
    GET /restaurants/{id}                restaurant detail   (RST-02)
    GET /restaurants/{id}/menu           menu + search/filters (MENU-01/02)

Owner management (D8 — auth + role + ownership, in that order):
    POST   /restaurants/{id}/menu        add a dish         (MENU-03)
    PUT    /menu-items/{id}              update dish        (MENU-04/05)
    DELETE /menu-items/{id}              soft-remove dish   (RST-03, D32)

Authorization policy (docs/authorization-matrix.md, AUTHZ-06):
role failure → 403; ownership failure (or unknown id) → 404, so a stranger
cannot even learn that another restaurant's dish exists.
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...core import constants as C
from ...core.config import Settings
from ...core.deps import build_get_current_user, require_menu_item_owner
from ...core.errors import ApiError
from ...db.engine import utcnow
from ...db.models import MenuItem, Restaurant, User
from ...db.session import SessionFactory
from ...schemas.pagination import MAX_PAGE_SIZE, DEFAULT_PAGE_SIZE, Page, PaginationParams
from ...schemas.restaurants import (
    PRICE_MAX_CENTS,
    CreateMenuItemIn,
    MenuItemOut,
    RestaurantOut,
    UpdateMenuItemIn,
)


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so user input is always a literal substring."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_restaurants_router(session_factory: SessionFactory, settings: Settings) -> APIRouter:
    router = APIRouter()
    get_current_user = build_get_current_user(session_factory, settings)
    Db = Annotated[Session, Depends(session_factory.get)]
    UserDep = Annotated[User, Depends(get_current_user)]
    # `Depends()` (not a bare model) is what makes FastAPI read the
    # pagination fields as *query* parameters instead of a request body.
    PageDep = Annotated[PaginationParams, Depends()]

    # --------------------------------------------------------------- public

    @router.get("/restaurants", response_model=Page[RestaurantOut])
    def list_restaurants(page: PageDep, db: Db) -> Page[RestaurantOut]:
        """Paginated public listing (RST-01, API-03)."""
        base = db.query(Restaurant)
        total = base.count()
        rows = (
            base.order_by(Restaurant.name, Restaurant.id)
            .offset(page.offset)
            .limit(page.limit)
            .all()
        )
        return Page(
            items=[RestaurantOut.model_validate(r) for r in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    @router.get("/restaurants/{restaurant_id}", response_model=RestaurantOut)
    def get_restaurant(restaurant_id: int, db: Db) -> RestaurantOut:
        """Restaurant detail; unknown id → 404 (RST-02, T-M5-02)."""
        restaurant = db.get(Restaurant, restaurant_id)
        if restaurant is None:
            raise ApiError(404, "NOT_FOUND", "Restaurant not found.")
        return RestaurantOut.model_validate(restaurant)

    @router.get(
        "/restaurants/{restaurant_id}/menu",
        response_model=Page[MenuItemOut],
        responses={404: {"description": "Unknown restaurant"}},
    )
    def list_menu(
        restaurant_id: int,
        page: PageDep,
        db: Db,
        search: Annotated[
            Optional[str],
            Query(max_length=120, description="Case-insensitive name substring."),
        ] = None,
        min_price_cents: Annotated[Optional[int], Query(ge=0, le=PRICE_MAX_CENTS)] = None,
        max_price_cents: Annotated[Optional[int], Query(ge=0, le=PRICE_MAX_CENTS)] = None,
    ) -> Page[MenuItemOut]:
        """A restaurant's menu with search + price filters (MENU-01/02).

        Unavailable (soft-removed) dishes stay visible, flagged
        ``available=false`` (T-M5-10); checkout excludes them (MENU-07, M6).
        Price bounds are inclusive.
        """
        if db.get(Restaurant, restaurant_id) is None:
            raise ApiError(404, "NOT_FOUND", "Restaurant not found.")
        query = db.query(MenuItem).filter(MenuItem.restaurant_id == restaurant_id)
        if search:
            query = query.filter(
                func.lower(MenuItem.name).like(f"%{_escape_like(search.lower())}%", escape="\\")
            )
        if min_price_cents is not None:
            query = query.filter(MenuItem.price_cents >= min_price_cents)
        if max_price_cents is not None:
            query = query.filter(MenuItem.price_cents <= max_price_cents)
        total = query.count()
        rows = (
            query.order_by(MenuItem.name, MenuItem.id)
            .offset(page.offset)
            .limit(page.limit)
            .all()
        )
        return Page(
            items=[MenuItemOut.model_validate(i) for i in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    # ------------------------------------------------- owner menu management

    @router.post(
        "/restaurants/{restaurant_id}/menu",
        response_model=MenuItemOut,
        status_code=201,
        responses={403: {"description": "Not an owner"}, 404: {"description": "Not the owner's restaurant"}},
    )
    def create_menu_item(
        restaurant_id: int, body: CreateMenuItemIn, user: UserDep, db: Db
    ) -> MenuItemOut:
        """Owner adds a dish to *their* restaurant (MENU-03, D2).

        No public restaurant creation exists (D2/D16): the restaurant must
        already exist and be the caller's (D24: an owner has at most one).
        """
        if user.role != C.ROLE_OWNER:
            raise ApiError(403, "ROLE_FORBIDDEN", "Only restaurant owners can manage menus.")
        restaurant = db.get(Restaurant, restaurant_id)
        if restaurant is None or restaurant.owner_id != user.id:
            raise ApiError(404, "NOT_FOUND", "Restaurant not found.")
        item = MenuItem(
            restaurant_id=restaurant.id,
            name=body.name.strip(),
            description=(body.description or "").strip() or None,
            price_cents=body.price_cents,
            available=body.available,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return MenuItemOut.model_validate(item)

    @router.put(
        "/menu-items/{menu_item_id}",
        response_model=MenuItemOut,
        responses={403: {"description": "Not an owner"}, 404: {"description": "Not the owner's dish"}},
    )
    def update_menu_item(menu_item_id: int, body: UpdateMenuItemIn, user: UserDep, db: Db) -> MenuItemOut:
        """Owner updates a dish: name/description/price/available (MENU-04/05).

        Partial update — only fields present in the body change. Historical
        order snapshots are unaffected by design (D3/D32).
        """
        item = require_menu_item_owner(user, db, menu_item_id)
        data = body.model_dump(exclude_unset=True)
        if not data:
            raise ApiError(422, "VALIDATION_ERROR", "No updatable fields provided.")
        if "name" in data and data["name"] is not None:
            item.name = data["name"].strip()
        if "description" in data:
            # None → keep; "" → clear; text → replace.
            if data["description"] is not None:
                item.description = data["description"].strip() or None
        if data.get("price_cents") is not None:
            item.price_cents = data["price_cents"]
        if data.get("available") is not None:
            item.available = data["available"]
        item.updated_at = utcnow()
        db.commit()
        db.refresh(item)
        return MenuItemOut.model_validate(item)

    @router.delete(
        "/menu-items/{menu_item_id}",
        status_code=204,
        responses={204: {"description": "Soft-removed"}, 403: {"description": "Not an owner"}, 404: {"description": "Not the owner's dish"}},
    )
    def delete_menu_item(menu_item_id: int, user: UserDep, db: Db) -> Response:
        """Owner soft-removes a dish (RST-03/D32): it becomes *unavailable*.

        The row is never hard-deleted — the public catalog keeps showing it
        (flagged) and past orders keep their snapshots (D3).
        """
        item = require_menu_item_owner(user, db, menu_item_id)
        item.available = False
        item.updated_at = utcnow()
        db.commit()
        return Response(status_code=204)

    return router
