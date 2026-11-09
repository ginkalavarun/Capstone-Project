"""M5 restaurant & menu tests (docs/test-plan.md §M5) plus the first
materialized halves of the M4 authorization tests (T-M4-14 endpoint sweep
and T-M4-16 two-owners isolation) for these endpoints.
"""
from types import SimpleNamespace

import pytest

from app.core import constants as C
from app.core import security
from app.db.engine import utcnow
from app.db.models import MenuItem, Order, OrderItem, Restaurant, User
from tests.test_auth import login_token  # reuse the login helper (same KNOWN_PASSWORD)

KNOWN_PASSWORD = "Correct-Horse-99x"
FAKE_HASH = "$2b$12$abcdefghijklmnopqrstuv" + "0" * 53  # padding rows never log in


def make_user(db_session, email: str, role: str, full_name: str = "Test User",
              password: str = KNOWN_PASSWORD) -> User:
    user = User(
        email=email,
        password_hash=security.hash_password(password),
        full_name=full_name,
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def make_restaurant(db_session, owner: User, name: str, fee: int = 200) -> Restaurant:
    restaurant = Restaurant(
        owner_id=owner.id, name=name, address=f"{name} HQ", delivery_fee_cents=fee
    )
    db_session.add(restaurant)
    db_session.flush()
    return restaurant


def make_item(db_session, restaurant: Restaurant, name: str, price: int,
              available: bool = True) -> MenuItem:
    item = MenuItem(
        restaurant_id=restaurant.id, name=name, price_cents=price, available=available
    )
    db_session.add(item)
    db_session.flush()
    return item


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def world(client, db_session):
    """Two owners (one restaurant each, D24), one customer, one partner."""
    owner_a = make_user(db_session, "owner-a@example.org", C.ROLE_OWNER, "Owner A")
    owner_b = make_user(db_session, "owner-b@example.org", C.ROLE_OWNER, "Owner B")
    customer = make_user(db_session, "cust@example.org", C.ROLE_CUSTOMER, "Customer")
    make_user(db_session, "partner@example.org", C.ROLE_PARTNER, "Partner")
    rest_a = make_restaurant(db_session, owner_a, "Alpha Bites", fee=250)
    rest_b = make_restaurant(db_session, owner_b, "Beta Bites", fee=350)
    items = {
        "chicken": make_item(db_session, rest_a, "Grilled Chicken", 1200),
        "soup_c": make_item(db_session, rest_a, "Ginger Chicken Soup", 500),
        "soup_v": make_item(db_session, rest_a, "Vegetable Soup", 400),
        "burger": make_item(db_session, rest_a, "Smash Burger", 800),
        "roll": make_item(db_session, rest_b, "Beta Roll", 600),
    }
    db_session.commit()
    return SimpleNamespace(
        owner_a=owner_a,
        owner_b=owner_b,
        customer=customer,
        rest_a=rest_a,
        rest_b=rest_b,
        items=items,
        tok_owner_a=login_token(client, "owner-a@example.org"),
        tok_owner_b=login_token(client, "owner-b@example.org"),
        tok_customer=login_token(client, "cust@example.org"),
        tok_partner=login_token(client, "partner@example.org"),
    )


def menu_url(restaurant_id: int) -> str:
    return f"/api/v1/restaurants/{restaurant_id}/menu"


# ---------------------------------------------------------------------------
# T-M5-01 — pagination (RST-01, API-03)
# ---------------------------------------------------------------------------

def test_m5_01_list_paginated(client, db_session, world):
    # Pad to 25 restaurants. D24: one restaurant per owner, so 23 more
    # owners. These padding users never log in, so a fake hash keeps the
    # suite fast (no bcrypt cost) — login behavior is tested in M4.
    for i in range(23):
        owner = User(
            email=f"pad{i:02d}@example.org",
            password_hash=FAKE_HASH,
            full_name=f"Pad Owner {i}",
            role=C.ROLE_OWNER,
            is_active=True,
        )
        db_session.add(owner)
        db_session.flush()
        db_session.add(Restaurant(owner_id=owner.id, name=f"Pad Place {i:02d}",
                                  address="x", delivery_fee_cents=100))
    db_session.commit()

    r = client.get("/api/v1/restaurants")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 25
    assert body["limit"] == 20 and body["offset"] == 0
    assert len(body["items"]) == 20

    p1 = client.get("/api/v1/restaurants", params={"limit": 10, "offset": 0}).json()
    p2 = client.get("/api/v1/restaurants", params={"limit": 10, "offset": 10}).json()
    p3 = client.get("/api/v1/restaurants", params={"limit": 10, "offset": 20}).json()
    assert (len(p1["items"]), len(p2["items"]), len(p3["items"])) == (10, 10, 5)
    assert p1["total"] == p2["total"] == p3["total"] == 25
    # disjoint pages, stable ordering
    assert {i["id"] for i in p1["items"]} & {i["id"] for i in p2["items"]} == set()
    assert [i["id"] for i in p1["items"]] == [i["id"] for i in body["items"]][:10]

    # bounded params → 422
    assert client.get("/api/v1/restaurants", params={"limit": 101}).status_code == 422
    assert client.get("/api/v1/restaurants", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/restaurants", params={"offset": -1}).status_code == 422


# ---------------------------------------------------------------------------
# T-M5-02 — detail + unknown id
# ---------------------------------------------------------------------------

def test_m5_02_detail(client, world):
    r = client.get(f"/api/v1/restaurants/{world.rest_a.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Alpha Bites"
    assert body["delivery_fee_cents"] == 250
    assert body["address"] == "Alpha Bites HQ"
    r = client.get("/api/v1/restaurants/99999")
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# T-M5-03 — menu listing carries full dish fields (MENU-01)
# ---------------------------------------------------------------------------

def test_m5_03_menu_and_dish_fields(client, world):
    body = client.get(menu_url(world.rest_a.id)).json()
    assert body["total"] == 4
    names = {i["name"] for i in body["items"]}
    assert names == {"Grilled Chicken", "Ginger Chicken Soup", "Vegetable Soup", "Smash Burger"}
    chicken = next(i for i in body["items"] if i["name"] == "Grilled Chicken")
    assert chicken["price_cents"] == 1200
    assert chicken["available"] is True
    assert chicken["restaurant_id"] == world.rest_a.id
    # restaurant B's dishes never leak into A's menu
    assert "Beta Roll" not in names
    # unknown restaurant → 404
    assert client.get(menu_url(99999)).status_code == 404


# ---------------------------------------------------------------------------
# T-M5-04 — name search (MENU-02)
# ---------------------------------------------------------------------------

def test_m5_04_search_by_name(client, world):
    base = menu_url(world.rest_a.id)
    body = client.get(base, params={"search": "chicken"}).json()
    assert [i["name"] for i in body["items"]] == ["Ginger Chicken Soup", "Grilled Chicken"]
    # case-insensitive
    assert client.get(base, params={"search": "CHICKEN"}).json()["total"] == 2
    # no matches → empty page (200, not 404)
    empty = client.get(base, params={"search": "zzz"}).json()
    assert empty["total"] == 0 and empty["items"] == []
    # LIKE wildcards in input are treated as literals
    assert client.get(base, params={"search": "%"}).json()["total"] == 0
    assert client.get(base, params={"search": "_"}).json()["total"] == 0


# ---------------------------------------------------------------------------
# T-M5-05 — price filter, inclusive bounds (MENU-02)
# ---------------------------------------------------------------------------

def test_m5_05_price_filter_inclusive(client, world):
    base = menu_url(world.rest_a.id)  # prices: 1200, 500, 400, 800
    r = client.get(base, params={"min_price_cents": 500, "max_price_cents": 800}).json()
    assert {i["price_cents"] for i in r["items"]} == {500, 800}  # both bounds included
    # just outside the lower bound drops exactly the 500 dish (prices: 1200/500/400/800)
    assert client.get(base, params={"min_price_cents": 501}).json()["total"] == 2  # 800 + 1200
    # just below the upper bound keeps exactly the 500 dish
    assert client.get(base, params={"max_price_cents": 499}).json()["total"] == 1
    assert client.get(base, params={"min_price_cents": 1200, "max_price_cents": 1200}).json()["total"] == 1
    assert client.get(base, params={"min_price_cents": 2000}).json()["total"] == 0
    # negative bounds are invalid input
    assert client.get(base, params={"min_price_cents": -1}).status_code == 422


# ---------------------------------------------------------------------------
# T-M5-06 — owner adds a dish (MENU-03)
# ---------------------------------------------------------------------------

def test_m5_06_owner_adds_dish(client, db_session, world):
    url = menu_url(world.rest_a.id)
    h = bearer(world.tok_owner_a)
    r = client.post(url, headers=h, json={"name": "New Curry", "price_cents": 750,
                                          "description": "spicy"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "New Curry" and body["price_cents"] == 750
    assert body["available"] is True and body["restaurant_id"] == world.rest_a.id
    # persisted and publicly visible
    assert client.get(url, params={"search": "curry"}).json()["total"] == 1

    # validation → 422 (never a 500, never a partial row)
    bad = [
        {"price_cents": 100},                                   # missing name
        {"name": "x" * 121, "price_cents": 100},               # name too long
        {"name": "   ", "price_cents": 100},                   # blank name
        {"name": "X", "price_cents": -5},                      # negative price
        {"name": "X", "price_cents": 10**9},                   # sanity cap
        {"name": "X", "price_cents": 100, "owner_id": 7},      # smuggled field
    ]
    for payload in bad:
        assert client.post(url, headers=h, json=payload).status_code == 422, payload
    db_session.expire_all()
    # 5 from the fixture + 1 from the valid post above; the bad posts created nothing
    assert db_session.query(MenuItem).count() == 6


# ---------------------------------------------------------------------------
# T-M5-07 — owner updates a dish (MENU-04)
# ---------------------------------------------------------------------------

def test_m5_07_owner_updates_dish(client, db_session, world):
    item = world.items["burger"]
    item.description = "original desc"
    db_session.commit()
    url = f"/api/v1/menu-items/{item.id}"
    h = bearer(world.tok_owner_a)

    r = client.put(url, headers=h, json={"name": "Mega Smash Burger", "price_cents": 950})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Mega Smash Burger" and body["price_cents"] == 950
    assert body["description"] == "original desc"  # untouched field preserved

    # clearing the description with ""
    r = client.put(url, headers=h, json={"description": ""})
    assert r.status_code == 200 and r.json()["description"] is None

    # persistence is visible through a fresh public read
    assert client.get(menu_url(world.rest_a.id), params={"search": "Mega"}).json()["total"] == 1

    # no fields → 422; unknown fields → 422 (extra=forbid)
    assert client.put(url, headers=h, json={}).status_code == 422
    assert client.put(url, headers=h, json={"hacker": True}).status_code == 422
    assert client.put(url, headers=h, json={"price_cents": -1}).status_code == 422


# ---------------------------------------------------------------------------
# T-M5-08 — availability toggle (MENU-05)
# ---------------------------------------------------------------------------

def test_m5_08_toggle_availability(client, world):
    item = world.items["roll"]
    url = f"/api/v1/menu-items/{item.id}"
    h = bearer(world.tok_owner_b)

    r = client.put(url, headers=h, json={"available": False})
    assert r.status_code == 200 and r.json()["available"] is False
    # reflected in the public catalog (still listed, flagged)
    row = next(i for i in client.get(menu_url(world.rest_b.id)).json()["items"]
               if i["id"] == item.id)
    assert row["available"] is False

    r = client.put(url, headers=h, json={"available": True})
    assert r.json()["available"] is True


# ---------------------------------------------------------------------------
# T-M5-09 / T-M4-14 — non-owner cannot modify (role 403, other owner 404)
# ---------------------------------------------------------------------------

OWNER_ENDPOINTS = [
    ("put", "/menu-items/{id}", {"price_cents": 1}),
    ("delete", "/menu-items/{id}", None),
    ("post", "/restaurants/{rid}/menu", {"name": "Sneaky Dish", "price_cents": 1}),
]


@pytest.mark.parametrize("method, path, payload", OWNER_ENDPOINTS)
def test_m4_14_endpoint_sweep_batch3(client, world, method, path, payload):
    """First materialized half of T-M4-14, for the batch-3 endpoints:
    no token → 401; wrong role → 403; right role, foreign resource → 404."""
    item_id = world.items["chicken"].id  # owned by owner A
    url = f"/api/v1{path.format(id=item_id, rid=world.rest_a.id)}"

    def call(url, token=None):
        kwargs = {}
        if token:
            kwargs["headers"] = bearer(token)
        if payload:  # `json` is only meaningful/accepted with a body
            kwargs["json"] = payload
        return getattr(client, method)(url, **kwargs)

    r = call(url)
    assert r.status_code == 401 and r.json()["code"] == "TOKEN_MISSING"
    r = call(url, world.tok_customer)
    assert r.status_code == 403 and r.json()["code"] == "ROLE_FORBIDDEN"
    assert call(url, world.tok_partner).status_code == 403
    r = call(url, world.tok_owner_b)
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"


def test_m4_16_owner_b_cannot_manage_restaurant_a(client, db_session, world):
    """T-M4-16 (batch-3 half): owner B has a *valid role* but zero access to
    restaurant A — and A's data must be untouched afterwards."""
    h = bearer(world.tok_owner_b)
    item = world.items["chicken"]
    price_before, available_before = item.price_cents, item.available

    assert client.post(menu_url(world.rest_a.id), headers=h,
                       json={"name": "Intrusion", "price_cents": 1}).status_code == 404
    assert client.put(f"/api/v1/menu-items/{item.id}", headers=h,
                      json={"price_cents": 1}).status_code == 404
    assert client.delete(f"/api/v1/menu-items/{item.id}", headers=h).status_code == 404

    db_session.expire_all()
    item = db_session.get(MenuItem, item.id)
    assert item.price_cents == price_before
    assert item.available is available_before
    assert db_session.query(MenuItem).filter_by(restaurant_id=world.rest_a.id).count() == 4


# ---------------------------------------------------------------------------
# T-M5-10 — soft delete (RST-03, D32): snapshot coherence
# ---------------------------------------------------------------------------

def test_m5_10_soft_delete_preserves_history(client, db_session, world):
    item = world.items["soup_v"]

    # A historical order that snapshots the dish (server-computed money, D3)
    order = Order(
        customer_id=world.customer.id,
        restaurant_id=world.rest_a.id,
        status=C.ORDER_DELIVERED,
        payment_status=C.PAYMENT_MOCK_PAID,
        items_subtotal_cents=400,
        delivery_fee_cents=250,
        total_cents=650,
        delivery_address="1 Student Ln",
        idempotency_key="soft-del-1",
        request_hash="a" * 64,
        status_updated_at=utcnow(),
        delivered_at=utcnow(),
    )
    db_session.add(order)
    db_session.flush()
    line = OrderItem(
        order_id=order.id,
        menu_item_id=item.id,
        item_name="Vegetable Soup",
        unit_price_cents=400,
        quantity=1,
        line_total_cents=400,
    )
    db_session.add(line)
    db_session.commit()

    r = client.delete(f"/api/v1/menu-items/{item.id}", headers=bearer(world.tok_owner_a))
    assert r.status_code == 204

    # the row still exists, now flagged unavailable, still publicly readable
    assert db_session.get(MenuItem, item.id) is not None
    row = next(i for i in client.get(menu_url(world.rest_a.id)).json()["items"]
               if i["id"] == item.id)
    assert row["available"] is False

    # the historical snapshot is untouched (D3)
    db_session.expire_all()
    line = db_session.get(OrderItem, line.id)
    assert line.item_name == "Vegetable Soup" and line.unit_price_cents == 400
    assert db_session.get(Order, order.id).status == C.ORDER_DELIVERED
