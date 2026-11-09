"""M6 checkout & order tests (docs/test-plan.md §M6).

Also materializes part of the two-customer isolation tests (T-M4-15) for
the order endpoints; the full sweep lands as more endpoints arrive in
batch 5.
"""
import threading
from types import SimpleNamespace

import pytest

from app.core import constants as C
from app.core import security
from app.db.models import MenuItem, Order, PaymentLedger, Restaurant, User
from app.schemas.orders import CheckoutIn
from app.services.checkout import place_order
from tests.test_auth import login_token

KNOWN_PASSWORD = "Correct-Horse-99x"


def make_user(db_session, email: str, role: str, full_name: str = "Test User") -> User:
    user = User(
        email=email,
        password_hash=security.hash_password(KNOWN_PASSWORD),
        full_name=full_name,
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def make_restaurant(db_session, owner: User, name: str, fee: int = 200) -> Restaurant:
    restaurant = Restaurant(owner_id=owner.id, name=name, address=f"{name} HQ",
                            delivery_fee_cents=fee)
    db_session.add(restaurant)
    db_session.flush()
    return restaurant


def make_item(db_session, restaurant: Restaurant, name: str, price: int,
              available: bool = True) -> MenuItem:
    item = MenuItem(restaurant_id=restaurant.id, name=name, price_cents=price,
                    available=available)
    db_session.add(item)
    db_session.flush()
    return item


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def world(client, db_session, db_factory):
    customer = make_user(db_session, "cust@example.org", C.ROLE_CUSTOMER, "Customer")
    customer2 = make_user(db_session, "cust2@example.org", C.ROLE_CUSTOMER, "Customer 2")
    owner = make_user(db_session, "owner@example.org", C.ROLE_OWNER, "Owner")
    owner2 = make_user(db_session, "owner2@example.org", C.ROLE_OWNER, "Owner 2")
    rest = make_restaurant(db_session, owner, "Main Bites", fee=250)
    rest2 = make_restaurant(db_session, owner2, "Side Rolls", fee=100)
    chicken = make_item(db_session, rest, "Grilled Chicken", 1200)
    fries = make_item(db_session, rest, "Fries", 400)
    gone = make_item(db_session, rest, "Gone Dish", 800, available=False)
    other = make_item(db_session, rest2, "Other Roll", 500)
    db_session.commit()
    return SimpleNamespace(
        customer=customer, customer2=customer2, owner=owner,
        rest=rest, rest2=rest2,
        chicken=chicken, fries=fries, gone=gone, other=other,
        tok_customer=login_token(client, "cust@example.org"),
        tok_customer2=login_token(client, "cust2@example.org"),
        tok_owner=login_token(client, "owner@example.org"),
    )


def make_body(world, key: str, items: list[dict] | None = None) -> dict:
    """A checkout body. Defaults: chicken ×2 + fries ×1 (see test comments)."""
    if items is None:
        items = [
            {"menu_item_id": world.chicken.id, "quantity": 2},
            {"menu_item_id": world.fries.id, "quantity": 1},
        ]
    return {
        "items": items,
        "delivery_address": "1 Student Ln",
        "idempotency_key": key,
    }


def default_total() -> int:
    """1200×2 + 400×1 + 250 fee = 3050 — the server-side truth (D3)."""
    return 1200 * 2 + 400 + 250


# ---------------------------------------------------------------------------
# T-M6-01 / CK-01 — place order
# ---------------------------------------------------------------------------

def test_m6_01_place_order(client, world):
    r = client.post("/api/v1/orders", headers=bearer(world.tok_customer),
                    json=make_body(world, "k1"))
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["status"] == C.ORDER_PLACED
    assert b["payment_status"] == C.PAYMENT_MOCK_PAID
    assert b["items_subtotal_cents"] == 1200 * 2 + 400
    assert b["delivery_fee_cents"] == 250
    assert b["total_cents"] == default_total()
    assert {i["item_name"] for i in b["items"]} == {"Grilled Chicken", "Fries"}
    assert b["delivery_address"] == "1 Student Ln"
    assert b["restaurant_id"] == world.rest.id
    assert b["restaurant_name"] == "Main Bites"


# ---------------------------------------------------------------------------
# T-M6-02 / CK-02 — client money is never authoritative
# ---------------------------------------------------------------------------

def test_m6_02_client_money_ignored(client, db_session, world):
    payload = make_body(world, "k2")
    payload["total_cents"] = 1                      # tampered
    payload["items"][0]["unit_price_cents"] = 1     # tampered line price
    payload["items"][0]["name"] = "Hacked Dish"     # tampered name
    payload["status"] = "DELIVERED"                 # tampered status
    payload["customer_id"] = 999                    # forged identity
    r = client.post("/api/v1/orders", headers=bearer(world.tok_customer), json=payload)
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["total_cents"] == default_total()      # server math won
    assert b["status"] == C.ORDER_PLACED
    assert all(i["unit_price_cents"] >= 400 for i in b["items"])
    assert all(i["item_name"] != "Hacked Dish" for i in b["items"])
    row = db_session.query(Order).filter_by(id=b["id"]).one()
    assert row.customer_id == world.customer.id     # token, not body


# ---------------------------------------------------------------------------
# T-M6-03 / CK-03 — snapshots survive later menu changes
# ---------------------------------------------------------------------------

def test_m6_03_snapshots_survive_menu_changes(client, world):
    r1 = client.post("/api/v1/orders", headers=bearer(world.tok_customer),
                     json=make_body(world, "k3"))
    order_id = r1.json()["id"]
    # The owner re-prices and renames the chicken *after* the order.
    r = client.put(f"/api/v1/menu-items/{world.chicken.id}",
                   headers=bearer(world.tok_owner),
                   json={"name": "Mega Chicken", "price_cents": 1999})
    assert r.status_code == 200
    detail = client.get(f"/api/v1/orders/{order_id}",
                        headers=bearer(world.tok_customer)).json()
    item = next(i for i in detail["items"] if i["menu_item_id"] == world.chicken.id)
    assert item["item_name"] == "Grilled Chicken"
    assert item["unit_price_cents"] == 1200
    assert detail["total_cents"] == default_total()


# ---------------------------------------------------------------------------
# T-M6-04 / CK-04, MENU-07 — invalid items: 422, nothing written
# ---------------------------------------------------------------------------

def test_m6_04_invalid_items_422_no_rows(client, db_session, world):
    before = db_session.query(Order).count()
    h = bearer(world.tok_customer)
    cases = [
        make_body(world, "k4a", [{"menu_item_id": world.gone.id, "quantity": 1}]),      # unavailable
        make_body(world, "k4b", [{"menu_item_id": 99999, "quantity": 1}]),              # missing
        make_body(world, "k4c", [                                                       # two restaurants
            {"menu_item_id": world.chicken.id, "quantity": 1},
            {"menu_item_id": world.other.id, "quantity": 1},
        ]),
    ]
    for payload in cases:
        r = client.post("/api/v1/orders", headers=h, json=payload)
        assert r.status_code == 422, payload
    assert db_session.query(Order).count() == before


# ---------------------------------------------------------------------------
# T-M6-05 / CK-04 — quantity & cart validation
# ---------------------------------------------------------------------------

def test_m6_05_quantity_validation(client, world):
    h = bearer(world.tok_customer)
    for qty in (0, -3, 101):
        r = client.post("/api/v1/orders", headers=h,
                        json=make_body(world, f"k5-{qty}",
                                       [{"menu_item_id": world.chicken.id, "quantity": qty}]))
        assert r.status_code == 422, qty
    r = client.post("/api/v1/orders", headers=h,
                    json=make_body(world, "k5-ss", [{"menu_item_id": world.chicken.id, "quantity": "two"}]))
    assert r.status_code == 422  # non-integer
    r = client.post("/api/v1/orders", headers=h, json=make_body(world, "k5-empty", []))
    assert r.status_code == 422  # empty cart


# ---------------------------------------------------------------------------
# T-M6-06 / CK-05, PAY-01 — payment ledger row
# ---------------------------------------------------------------------------

def test_m6_06_payment_record(client, db_session, world):
    r = client.post("/api/v1/orders", headers=bearer(world.tok_customer),
                    json=make_body(world, "k6"))
    assert r.status_code == 201
    row = db_session.query(Order).filter_by(id=r.json()["id"]).one()
    assert row.payment_status == C.PAYMENT_MOCK_PAID
    rows = db_session.query(PaymentLedger).filter_by(order_id=row.id).all()
    assert len(rows) == 1
    assert rows[0].type == C.PAYMENT_MOCK_PAID
    assert rows[0].amount_cents == row.total_cents == default_total()


# ---------------------------------------------------------------------------
# T-M6-07 / CK-06 — exact integer-cent math, incl. fee and merged lines
# ---------------------------------------------------------------------------

def test_m6_07_total_math(client, world):
    h = bearer(world.tok_customer)
    # 1200×1 + 400×3 = 2400; + 250 fee = 2650
    r = client.post("/api/v1/orders", headers=h, json=make_body(
        world, "k7a", [
            {"menu_item_id": world.chicken.id, "quantity": 1},
            {"menu_item_id": world.fries.id, "quantity": 3},
        ]))
    b = r.json()
    assert (b["items_subtotal_cents"], b["delivery_fee_cents"], b["total_cents"]) == (2400, 250, 2650)

    # duplicate lines merge into one receipt line: 2 + 3 = 5 @ 1200 = 6000
    r = client.post("/api/v1/orders", headers=h, json=make_body(
        world, "k7b", [
            {"menu_item_id": world.chicken.id, "quantity": 2},
            {"menu_item_id": world.chicken.id, "quantity": 3},
        ]))
    b = r.json()
    assert len(b["items"]) == 1
    assert b["items"][0]["quantity"] == 5
    assert b["items"][0]["line_total_cents"] == 6000
    assert b["total_cents"] == 6000 + 250


# ---------------------------------------------------------------------------
# T-M6-08 / ORDR-01 — own history, filters, pagination (+ T-M4-15 half)
# ---------------------------------------------------------------------------

def test_m6_08_own_history_filters(client, db_session, world):
    h = bearer(world.tok_customer)
    o1 = client.post("/api/v1/orders", headers=h, json=make_body(world, "k8a")).json()
    o2 = client.post("/api/v1/orders", headers=h, json=make_body(world, "k8b")).json()
    client.post("/api/v1/orders", headers=h, json=make_body(world, "k8c"))
    # Push one order to DELIVERED directly (lifecycle mutations are batch 5).
    row1 = db_session.get(Order, o1["id"])
    row1.status = C.ORDER_DELIVERED
    db_session.commit()
    # customer2 places their own, unrelated order.
    client.post("/api/v1/orders", headers=bearer(world.tok_customer2),
                json=make_body(world, "k8d", [{"menu_item_id": world.fries.id, "quantity": 1}]))

    lst = client.get("/api/v1/orders", headers=h).json()
    assert lst["total"] == 3                      # own only, not customer2's
    assert lst["limit"] == 20 and lst["offset"] == 0

    assert client.get("/api/v1/orders", headers=h,
                      params={"status": C.ORDER_DELIVERED}).json()["total"] == 1
    assert client.get("/api/v1/orders", headers=h,
                      params={"status": C.ORDER_PLACED}).json()["total"] == 2
    assert client.get("/api/v1/orders", headers=h,
                      params={"status": "BOGUS"}).status_code == 422
    assert client.get("/api/v1/orders", headers=h,
                      params={"date_from": "2999-01-01"}).json()["total"] == 0
    assert client.get("/api/v1/orders", headers=h,
                      params={"date_to": "1999-01-01"}).json()["total"] == 0

    # T-M4-15 (batch-4 half): customer2 cannot read customer A's order.
    assert client.get(f"/api/v1/orders/{o1['id']}",
                      headers=bearer(world.tok_customer2)).status_code == 404
    # but the owner of the restaurant may read it.
    assert client.get(f"/api/v1/orders/{o1['id']}",
                      headers=bearer(world.tok_owner)).status_code == 200


# ---------------------------------------------------------------------------
# T-M6-09 / ORDR-02 — detail shape
# ---------------------------------------------------------------------------

def test_m6_09_detail_shape(client, world):
    r = client.post("/api/v1/orders", headers=bearer(world.tok_customer),
                    json=make_body(world, "k9"))
    d = client.get(f"/api/v1/orders/{r.json()['id']}",
                   headers=bearer(world.tok_customer)).json()
    for k in ("id", "status", "payment_status", "status_updated_at", "delivered_at",
              "items_subtotal_cents", "delivery_fee_cents", "total_cents",
              "delivery_address", "restaurant_name", "created_at"):
        assert k in d, k
    assert d["delivered_at"] is None
    assert d["restaurant_name"] == "Main Bites"
    for i in d["items"]:
        for k in ("item_name", "unit_price_cents", "quantity", "line_total_cents"):
            assert k in i, k


# ---------------------------------------------------------------------------
# T-M6-10 / CK-07 — idempotency key bounds (D34)
# ---------------------------------------------------------------------------

def test_m6_10_idempotency_key_boundaries(client, db_session, world):
    h = bearer(world.tok_customer)
    payload = make_body(world, "k10")
    del payload["idempotency_key"]
    assert client.post("/api/v1/orders", headers=h, json=payload).status_code == 422
    assert client.post("/api/v1/orders", headers=h,
                       json=make_body(world, "x" * 65)).status_code == 422
    assert client.post("/api/v1/orders", headers=h,
                       json=make_body(world, "x" * 64)).status_code == 201
    assert client.post("/api/v1/orders", headers=h,
                       json=make_body(world, "z")).status_code == 201


# ---------------------------------------------------------------------------
# T-M6-11 / CK-08 — identical retry returns the original order
# ---------------------------------------------------------------------------

def test_m6_11_identical_retry(client, db_session, world):
    h = bearer(world.tok_customer)
    r1 = client.post("/api/v1/orders", headers=h, json=make_body(world, "retry-key-1"))
    assert r1.status_code == 201
    r2 = client.post("/api/v1/orders", headers=h, json=make_body(world, "retry-key-1"))
    assert r2.status_code == 200  # retry, not a new creation
    assert r2.json()["id"] == r1.json()["id"]
    assert db_session.query(Order).count() == 1
    assert db_session.query(PaymentLedger).count() == 1


# ---------------------------------------------------------------------------
# T-M6-12 / CK-09 — same key, different payload → 409
# ---------------------------------------------------------------------------

def test_m6_12_key_reuse_different_payload(client, db_session, world):
    h = bearer(world.tok_customer)
    r1 = client.post("/api/v1/orders", headers=h,
                     json=make_body(world, "reuse-key-1",
                                    [{"menu_item_id": world.chicken.id, "quantity": 1}]))
    assert r1.status_code == 201
    r2 = client.post("/api/v1/orders", headers=h,
                     json=make_body(world, "reuse-key-1",
                                    [{"menu_item_id": world.fries.id, "quantity": 1}]))
    assert r2.status_code == 409 and r2.json()["code"] == "IDEMPOTENCY_MISMATCH"
    assert db_session.query(Order).count() == 1
    detail = client.get(f"/api/v1/orders/{r1.json()['id']}", headers=h).json()
    assert detail["total_cents"] == 1200 + 250  # the original is intact


# ---------------------------------------------------------------------------
# T-M6-13 / CK-10 — competing identical checkouts: exactly one order
# ---------------------------------------------------------------------------

def test_m6_13_competing_checkouts_one_row(client, db_session, db_factory, world):
    key = "race-key-1"
    # A plain attribute bag is all the service needs (id + role); it keeps the
    # threads from touching the fixture's ORM object across sessions.
    fake_user = SimpleNamespace(id=world.customer.id, role=C.ROLE_CUSTOMER)
    results: list[tuple[int, bool]] = []
    errors: list[BaseException] = []

    def attempt() -> None:
        s = db_factory.create()
        try:
            payload = CheckoutIn(**make_body(world, key))
            order, created = place_order(s, fake_user, payload)  # type: ignore[arg-type]
            results.append((order.id, created))
        except BaseException as e:  # noqa: BLE001 — surfaced, never swallowed
            errors.append(e)
        finally:
            s.close()

    threads = [threading.Thread(target=attempt) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors, errors
    assert len({oid for oid, _ in results}) == 1  # one winner's order for all
    db_session.expire_all()
    assert db_session.query(Order).filter_by(idempotency_key=key).count() == 1
    assert db_session.query(PaymentLedger).count() == 1  # no double payment


# ---------------------------------------------------------------------------
# T-M6-14 / D34 — keys are customer-scoped, not global
# ---------------------------------------------------------------------------

def test_m6_14_cross_customer_key_isolation(client, db_session, world):
    key = "shared-key-1"
    a = client.post("/api/v1/orders", headers=bearer(world.tok_customer),
                    json=make_body(world, key))
    b = client.post("/api/v1/orders", headers=bearer(world.tok_customer2),
                    json=make_body(world, key))
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["id"] != b.json()["id"]  # distinct orders
    assert db_session.query(Order).filter_by(idempotency_key=key).count() == 2
    # A's order is untouched by B's reuse of the key string.
    detail = client.get(f"/api/v1/orders/{a.json()['id']}",
                        headers=bearer(world.tok_customer)).json()
    assert detail["total_cents"] == default_total()
    assert detail["customer_id"] == world.customer.id
