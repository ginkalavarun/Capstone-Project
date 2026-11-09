"""M7 lifecycle & delivery tests (docs/test-plan.md §M7).

Also materializes the remaining deferred halves of the M4 isolation tests
where order endpoints are involved (two owners / two partners, T-M4-16/17).
"""
import threading
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core import constants as C
from app.core import security
from app.core.errors import ApiError
from app.db.engine import utcnow
from app.db.models import (
    MenuItem,
    Order,
    OrderItem,
    PaymentLedger,
    Restaurant,
    User,
)
from tests.test_auth import login_token

KNOWN_PASSWORD = "Correct-Horse-99x"


def make_user(db_session, email: str, role: str, full_name: str = "Test User",
              active: bool = True) -> User:
    user = User(
        email=email,
        password_hash=security.hash_password(KNOWN_PASSWORD),
        full_name=full_name,
        role=role,
        is_active=active,
    )
    db_session.add(user)
    db_session.flush()
    return user


def make_restaurant(db_session, owner: User, name: str, fee: int = 250) -> Restaurant:
    restaurant = Restaurant(owner_id=owner.id, name=name, address=f"{name} HQ",
                            delivery_fee_cents=fee)
    db_session.add(restaurant)
    db_session.flush()
    return restaurant


def make_item(db_session, restaurant: Restaurant, name: str, price: int) -> MenuItem:
    item = MenuItem(restaurant_id=restaurant.id, name=name, price_cents=price,
                    available=True)
    db_session.add(item)
    db_session.flush()
    return item


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_order(db_session, customer: User, restaurant: Restaurant, item: MenuItem, *,
               status: str, partner: User | None = None, fee: int = 250,
               age_minutes: int = 10) -> Order:
    """Seed an order (with snapshot line + ledger) in a given state.

    `age_minutes` backdates created_at/status_updated_at so timestamp
    assertions have something to compare against. CANCELLED/REFUNDED seeds
    carry the consistent payment history (D29/D30).
    """
    now = utcnow()
    created = now - timedelta(minutes=age_minutes)
    paid = status not in (C.ORDER_CANCELLED, C.ORDER_REFUNDED)
    order = Order(
        customer_id=customer.id,
        restaurant_id=restaurant.id,
        delivery_partner_id=partner.id if partner else None,
        status=status,
        payment_status=C.PAYMENT_MOCK_PAID if paid else C.PAYMENT_REFUNDED,
        status_updated_at=created,
        delivered_at=now - timedelta(minutes=1)
        if status in (C.ORDER_DELIVERED, C.ORDER_REFUNDED)
        else None,
        items_subtotal_cents=item.price_cents,
        delivery_fee_cents=fee,
        total_cents=item.price_cents + fee,
        delivery_address="1 Student Ln",
        idempotency_key=f"seed-{uuid.uuid4().hex[:12]}",
        request_hash="a" * 64,
        created_at=created,
        updated_at=created,
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(OrderItem(
        order_id=order.id, menu_item_id=item.id, item_name=item.name,
        unit_price_cents=item.price_cents, quantity=1,
        line_total_cents=item.price_cents,
    ))
    db_session.add(PaymentLedger(order_id=order.id, type=C.PAYMENT_MOCK_PAID,
                                 amount_cents=order.total_cents, created_at=created))
    if not paid:
        db_session.add(PaymentLedger(order_id=order.id, type=C.PAYMENT_REFUNDED,
                                     amount_cents=order.total_cents))
    db_session.commit()
    return order


@pytest.fixture()
def world(client, db_session, db_factory):
    customer1 = make_user(db_session, "cust1@example.org", C.ROLE_CUSTOMER, "Cust 1")
    customer2 = make_user(db_session, "cust2@example.org", C.ROLE_CUSTOMER, "Cust 2")
    owner1 = make_user(db_session, "own1@example.org", C.ROLE_OWNER, "Owner 1")
    owner2 = make_user(db_session, "own2@example.org", C.ROLE_OWNER, "Owner 2")
    partner1 = make_user(db_session, "dp1@example.org", C.ROLE_PARTNER, "Partner 1")
    partner2 = make_user(db_session, "dp2@example.org", C.ROLE_PARTNER, "Partner 2")
    partner_off = make_user(db_session, "dp-off@example.org", C.ROLE_PARTNER,
                            "Partner Off", active=False)
    rest1 = make_restaurant(db_session, owner1, "Alpha", fee=250)
    rest2 = make_restaurant(db_session, owner2, "Beta", fee=350)
    item1 = make_item(db_session, rest1, "Grilled Chicken", 1200)
    make_item(db_session, rest2, "Beta Roll", 500)
    db_session.commit()
    return SimpleNamespace(
        customer1=customer1, customer2=customer2, owner1=owner1, owner2=owner2,
        partner1=partner1, partner2=partner2, partner_off=partner_off,
        rest1=rest1, rest2=rest2, item1=item1,
        tok_customer1=login_token(client, "cust1@example.org"),
        tok_customer2=login_token(client, "cust2@example.org"),
        tok_owner1=login_token(client, "own1@example.org"),
        tok_owner2=login_token(client, "own2@example.org"),
        tok_partner1=login_token(client, "dp1@example.org"),
        tok_partner2=login_token(client, "dp2@example.org"),
    )


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


# ---------------------------------------------------------------------------
# T-M7-01 / ORDER-01, ORDER-08 — the full transition map
# ---------------------------------------------------------------------------

def _sweep_cases(world) -> list[tuple[str, dict | None, str, str, str]]:
    """(endpoint, body, actor-attr, from_status, expected_to|None) for every
    action × every from-status (63 cases)."""
    actions = [
        ("cancel", None, "tok_customer1", C.ORDER_PLACED, C.ORDER_CANCELLED),
        ("accept", None, "tok_owner1", C.ORDER_PLACED, C.ORDER_ACCEPTED),
        ("status", {"status": C.ORDER_PREPARING}, "tok_owner1",
         C.ORDER_ACCEPTED, C.ORDER_PREPARING),
        ("status", {"status": C.ORDER_READY}, "tok_owner1",
         C.ORDER_PREPARING, C.ORDER_READY),
        ("assign", {"delivery_partner_id": world.partner1.id}, "tok_owner1",
         C.ORDER_READY, C.ORDER_ASSIGNED),
        ("delivery-status", {"status": C.ORDER_OUT_FOR_DELIVERY}, "tok_partner1",
         C.ORDER_ASSIGNED, C.ORDER_OUT_FOR_DELIVERY),
        ("delivery-status", {"status": C.ORDER_DELIVERED}, "tok_partner1",
         C.ORDER_OUT_FOR_DELIVERY, C.ORDER_DELIVERED),
    ]
    cases = []
    for endpoint, body, actor, valid_from, to in actions:
        for from_status in C.ORDER_STATUSES:
            cases.append((endpoint, body, actor, from_status,
                          to if from_status == valid_from else None))
    return cases


def test_m7_01_full_map_sweep(client, db_session, world):
    """Every (from, action) pair: the one valid edge succeeds with the
    correct actor; every other pair is 409 INVALID_TRANSITION (D7, ORDER-08).

    Orders for delivery actions are seeded with the acting partner attached
    so the *edge* — not ownership — is what is under test.
    """
    cases = _sweep_cases(world)
    assert len(cases) == 63
    for endpoint, body, actor_attr, from_status, expected_to in cases:
        partner = world.partner1 if endpoint == "delivery-status" else None
        order = make_order(db_session, world.customer1, world.rest1, world.item1,
                           status=from_status, partner=partner)
        token = getattr(world, actor_attr)
        r = client.post(f"/api/v1/orders/{order.id}/{endpoint}",
                        headers=bearer(token), json=body)
        if expected_to is None:
            assert r.status_code == 409, (endpoint, from_status, r.text)
            assert r.json()["code"] == "INVALID_TRANSITION"
        else:
            assert r.status_code == 200, (endpoint, from_status, r.text)
            assert r.json()["status"] == expected_to, (endpoint, from_status)
            db_session.expire_all()
            assert db_session.get(Order, order.id).status == expected_to


# ---------------------------------------------------------------------------
# T-M7-02/03/04 / ORDER-02, ORDER-03 — cancellation rules
# ---------------------------------------------------------------------------

def test_m7_02_cancel_from_placed(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_PLACED)
    r = client.post(f"/api/v1/orders/{order.id}/cancel",
                    headers=bearer(world.tok_customer1))
    assert r.status_code == 200
    assert r.json()["status"] == C.ORDER_CANCELLED
    # someone else's customer cannot cancel it (404, not 403 — AUTHZ-06)
    r = client.post(f"/api/v1/orders/{order.id}/cancel",
                    headers=bearer(world.tok_customer2))
    assert r.status_code == 404
    # a non-customer role gets 403
    r = client.post(f"/api/v1/orders/{order.id}/cancel",
                    headers=bearer(world.tok_owner1))
    assert r.status_code == 403


@pytest.mark.parametrize("from_status", [
    C.ORDER_ACCEPTED, C.ORDER_PREPARING, C.ORDER_READY, C.ORDER_ASSIGNED,
    C.ORDER_OUT_FOR_DELIVERY, C.ORDER_DELIVERED, C.ORDER_CANCELLED,
    C.ORDER_REFUNDED,
])
def test_m7_03_04_cancel_rejected_after_placed(client, db_session, world, from_status):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=from_status)
    r = client.post(f"/api/v1/orders/{order.id}/cancel",
                    headers=bearer(world.tok_customer1))
    assert r.status_code == 409 and r.json()["code"] == "INVALID_TRANSITION"
    db_session.expire_all()
    assert db_session.get(Order, order.id).status == from_status  # untouched


# ---------------------------------------------------------------------------
# T-M7-05 / ORDER-04 — accept
# ---------------------------------------------------------------------------

def test_m7_05_accept(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_PLACED)
    # the owning owner can accept
    r = client.post(f"/api/v1/orders/{order.id}/accept",
                    headers=bearer(world.tok_owner1))
    assert r.status_code == 200 and r.json()["status"] == C.ORDER_ACCEPTED
    # another owner → 404 (T-M4-16 half: role valid, resource foreign)
    r = client.post(f"/api/v1/orders/{order.id}/accept",
                    headers=bearer(world.tok_owner2))
    assert r.status_code == 404
    # customer → 403
    r = client.post(f"/api/v1/orders/{order.id}/accept",
                    headers=bearer(world.tok_customer1))
    assert r.status_code == 403
    # wrong status → 409
    ready = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_READY)
    r = client.post(f"/api/v1/orders/{ready.id}/accept",
                    headers=bearer(world.tok_owner1))
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# T-M7-06 / ORDER-05 — prep chain, no skipping
# ---------------------------------------------------------------------------

def test_m7_06_prep_chain(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_PLACED)
    h = bearer(world.tok_owner1)
    assert client.post(f"/api/v1/orders/{order.id}/accept", headers=h).status_code == 200
    r = client.post(f"/api/v1/orders/{order.id}/status", headers=h,
                    json={"status": C.ORDER_PREPARING})
    assert r.status_code == 200 and r.json()["status"] == C.ORDER_PREPARING
    r = client.post(f"/api/v1/orders/{order.id}/status", headers=h,
                    json={"status": C.ORDER_READY})
    assert r.status_code == 200 and r.json()["status"] == C.ORDER_READY
    # skipping a step (PLACED → READY) is not an edge
    fresh = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_PLACED)
    r = client.post(f"/api/v1/orders/{fresh.id}/status", headers=h,
                    json={"status": C.ORDER_READY})
    assert r.status_code == 409
    # an unknown target is invalid input, not a transition error
    r = client.post(f"/api/v1/orders/{order.id}/status", headers=h,
                    json={"status": "TELEPORTED"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# T-M7-07/08 / ORDER-06 — assignment rules
# ---------------------------------------------------------------------------

def test_m7_07_assign_only_from_ready(client, db_session, world):
    h = bearer(world.tok_owner1)
    preparing = make_order(db_session, world.customer1, world.rest1, world.item1,
                           status=C.ORDER_PREPARING)
    r = client.post(f"/api/v1/orders/{preparing.id}/assign", headers=h,
                    json={"delivery_partner_id": world.partner1.id})
    assert r.status_code == 409
    ready = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_READY)
    r = client.post(f"/api/v1/orders/{ready.id}/assign", headers=h,
                    json={"delivery_partner_id": world.partner1.id})
    assert r.status_code == 200
    assert r.json()["status"] == C.ORDER_ASSIGNED
    assert r.json()["delivery_partner_id"] == world.partner1.id
    # another owner cannot assign on this restaurant's order (404)
    r = client.post(f"/api/v1/orders/{ready.id}/assign", headers=bearer(world.tok_owner2),
                    json={"delivery_partner_id": world.partner2.id})
    assert r.status_code == 404


def test_m7_08_partner_validity(client, db_session, world):
    h = bearer(world.tok_owner1)
    ready = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_READY)
    url = f"/api/v1/orders/{ready.id}/assign"
    # a customer is not a partner
    r = client.post(url, headers=h, json={"delivery_partner_id": world.customer2.id})
    assert r.status_code == 422
    # a deactivated partner is not assignable (D5)
    r = client.post(url, headers=h, json={"delivery_partner_id": world.partner_off.id})
    assert r.status_code == 422
    # a nonexistent id
    r = client.post(url, headers=h, json={"delivery_partner_id": 99999})
    assert r.status_code == 422
    db_session.expire_all()
    assert db_session.get(Order, ready.id).delivery_partner_id is None


# ---------------------------------------------------------------------------
# T-M7-09/10 / ORDER-07, DELV — partner transitions
# ---------------------------------------------------------------------------

def test_m7_09_partner_transitions(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_READY, partner=world.partner1)
    h = bearer(world.tok_partner1)
    r = client.post(f"/api/v1/orders/{order.id}/accept", headers=h)
    assert r.status_code == 403  # partners run no owner actions
    r = client.post(f"/api/v1/orders/{order.id}/delivery-status", headers=h,
                    json={"status": C.ORDER_OUT_FOR_DELIVERY})
    assert r.status_code == 409  # not yet ASSIGNED — the edge does not match
    # assign, then the assigned partner drives the delivery edges
    client.post(f"/api/v1/orders/{order.id}/assign", headers=bearer(world.tok_owner1),
                json={"delivery_partner_id": world.partner1.id})
    r = client.post(f"/api/v1/orders/{order.id}/delivery-status", headers=h,
                    json={"status": C.ORDER_OUT_FOR_DELIVERY})
    assert r.status_code == 200 and r.json()["status"] == C.ORDER_OUT_FOR_DELIVERY
    r = client.post(f"/api/v1/orders/{order.id}/delivery-status", headers=h,
                    json={"status": C.ORDER_DELIVERED})
    assert r.status_code == 200
    assert r.json()["status"] == C.ORDER_DELIVERED
    assert r.json()["delivered_at"] is not None  # D31: review eligibility anchor
    db_session.expire_all()
    assert db_session.get(Order, order.id).payment_status == C.PAYMENT_MOCK_PAID


def test_m7_10_non_assigned_partner_denied(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_ASSIGNED, partner=world.partner1)
    h = bearer(world.tok_partner2)  # a real partner, but not this order's
    r = client.post(f"/api/v1/orders/{order.id}/delivery-status", headers=h,
                    json={"status": C.ORDER_OUT_FOR_DELIVERY})
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"
    r = client.get(f"/api/v1/delivery/orders/{order.id}", headers=h)
    assert r.status_code == 404  # T-M4-17 half: no peeking at others' work
    db_session.expire_all()
    assert db_session.get(Order, order.id).status == C.ORDER_ASSIGNED  # untouched


# ---------------------------------------------------------------------------
# T-M7-11/12 / ORDER-09, ORDER-10 — timestamps + customer tracking
# ---------------------------------------------------------------------------

def test_m7_11_timestamps_move_on_real_transitions(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_PLACED, age_minutes=30)
    before = parse_ts(
        client.get(f"/api/v1/orders/{order.id}", headers=bearer(world.tok_customer1))
        .json()["status_updated_at"]
    )
    client.post(f"/api/v1/orders/{order.id}/accept", headers=bearer(world.tok_owner1))
    after = parse_ts(
        client.get(f"/api/v1/orders/{order.id}", headers=bearer(world.tok_customer1))
        .json()["status_updated_at"]
    )
    assert after > before  # the transition stamped a newer time (UTC)


def test_m7_12_customer_tracks_full_lifecycle(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_READY, partner=world.partner1)
    h = bearer(world.tok_customer1)
    client.post(f"/api/v1/orders/{order.id}/assign", headers=bearer(world.tok_owner1),
                json={"delivery_partner_id": world.partner1.id})
    client.post(f"/api/v1/orders/{order.id}/delivery-status",
                headers=bearer(world.tok_partner1),
                json={"status": C.ORDER_OUT_FOR_DELIVERY})
    client.post(f"/api/v1/orders/{order.id}/delivery-status",
                headers=bearer(world.tok_partner1),
                json={"status": C.ORDER_DELIVERED})
    d = client.get(f"/api/v1/orders/{order.id}", headers=h).json()
    assert d["status"] == C.ORDER_DELIVERED
    assert d["delivered_at"] is not None
    assert d["payment_status"] == C.PAYMENT_MOCK_PAID
    assert d["items"][0]["item_name"] == "Grilled Chicken"  # snapshot


# ---------------------------------------------------------------------------
# T-M7-13/14/15 / DELV-01/02/03 — partner lists & detail
# ---------------------------------------------------------------------------

def test_m7_13_14_15_partner_views(client, db_session, world):
    # partner1's workload: one ASSIGNED, one READY (unassigned — not theirs)
    a1 = make_order(db_session, world.customer1, world.rest1, world.item1,
                    status=C.ORDER_ASSIGNED, partner=world.partner1)
    a2 = make_order(db_session, world.customer2, world.rest1, world.item1,
                    status=C.ORDER_OUT_FOR_DELIVERY, partner=world.partner1)
    other = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_ASSIGNED, partner=world.partner2)
    # past: one delivered, one delivered-then-refunded
    done1 = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_DELIVERED, partner=world.partner1)
    done2 = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_REFUNDED, partner=world.partner1)
    hp = bearer(world.tok_partner1)

    active = client.get("/api/v1/delivery/orders", headers=hp).json()
    assert active["total"] == 2  # a1 + a2 — NOT partner2's, not the done ones
    assert {i["status"] for i in active["items"]} == {C.ORDER_ASSIGNED,
                                                      C.ORDER_OUT_FOR_DELIVERY}
    # status filter
    assert client.get("/api/v1/delivery/orders", headers=hp,
                      params={"status": C.ORDER_ASSIGNED}).json()["total"] == 1
    # history = past completed assignments
    hist = client.get("/api/v1/delivery/history", headers=hp).json()
    assert hist["total"] == 2
    assert {i["status"] for i in hist["items"]} == {C.ORDER_DELIVERED,
                                                    C.ORDER_REFUNDED}

    # detail for an assigned order includes the customer's delivery details
    d = client.get(f"/api/v1/delivery/orders/{a1.id}", headers=hp).json()
    assert d["delivery_address"] == "1 Student Ln"
    assert d["customer_name"] == "Cust 1"
    # a customer listing the partner endpoints → 403
    assert client.get("/api/v1/delivery/orders",
                      headers=bearer(world.tok_customer1)).status_code == 403


# ---------------------------------------------------------------------------
# T-M7-16 / DELV-04, D5 — partner listing for owners
# ---------------------------------------------------------------------------

def test_m7_16_partner_listing_for_owners(client, db_session, world):
    r = client.get("/api/v1/delivery-partners", headers=bearer(world.tok_owner1))
    assert r.status_code == 200
    body = r.json()
    names = {p["full_name"] for p in body}
    assert names == {"Partner 1", "Partner 2"}  # the deactivated one is excluded
    for p in body:
        assert set(p) == {"id", "full_name"}  # minimal PII (D5): no emails
    # non-owner → 403
    assert client.get("/api/v1/delivery-partners",
                      headers=bearer(world.tok_customer1)).status_code == 403
    assert client.get("/api/v1/delivery-partners",
                      headers=bearer(world.tok_partner1)).status_code == 403


# ---------------------------------------------------------------------------
# T-M7-17 / ORDER-11 — no re-stamp on a no-op re-POST
# ---------------------------------------------------------------------------

def test_m7_17_no_restamp_on_noop(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_ACCEPTED, age_minutes=20)
    stamp_before = client.get(f"/api/v1/orders/{order.id}",
                              headers=bearer(world.tok_customer1)).json()["status_updated_at"]
    # re-POSTing the current state is a rejected (no-op) transition
    r = client.post(f"/api/v1/orders/{order.id}/status", headers=bearer(world.tok_owner1),
                    json={"status": C.ORDER_ACCEPTED})
    assert r.status_code == 409  # ACCEPTED→ACCEPTED is not an edge
    stamp_after = client.get(f"/api/v1/orders/{order.id}",
                             headers=bearer(world.tok_customer1)).json()["status_updated_at"]
    assert stamp_before == stamp_after  # reminder clock untouched (D6)
    db_session.expire_all()
    assert db_session.get(Order, order.id).status == C.ORDER_ACCEPTED


# ---------------------------------------------------------------------------
# T-M7-18 / D29 — cancellation = full mock reversal
# ---------------------------------------------------------------------------

def test_m7_18_cancellation_reversal(client, db_session, world):
    from app.db.models import RefundRequest

    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_PLACED, fee=250)
    total = order.total_cents  # 1450 = 1200 + 250
    r = client.post(f"/api/v1/orders/{order.id}/cancel",
                    headers=bearer(world.tok_customer1))
    assert r.status_code == 200
    assert r.json()["status"] == C.ORDER_CANCELLED
    assert r.json()["payment_status"] == C.PAYMENT_REFUNDED
    assert r.json()["delivered_at"] is None
    db_session.expire_all()
    rows = db_session.query(PaymentLedger).filter_by(order_id=order.id).all()
    assert [(x.type, x.amount_cents) for x in rows] == [
        (C.PAYMENT_MOCK_PAID, total), (C.PAYMENT_REFUNDED, total)
    ]  # full reversal incl. fee (D27)
    assert db_session.query(RefundRequest).filter_by(order_id=order.id).count() == 0


# ---------------------------------------------------------------------------
# T-M7-19 / D29 — duplicate cancellation: 409, no duplicate reversal
# ---------------------------------------------------------------------------

def test_m7_19_duplicate_cancellation(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_PLACED)
    assert client.post(f"/api/v1/orders/{order.id}/cancel",
                       headers=bearer(world.tok_customer1)).status_code == 200
    r = client.post(f"/api/v1/orders/{order.id}/cancel",
                    headers=bearer(world.tok_customer1))
    assert r.status_code == 409 and r.json()["code"] == "INVALID_TRANSITION"
    db_session.expire_all()
    rows = db_session.query(PaymentLedger).filter_by(order_id=order.id).all()
    assert [x.type for x in rows] == [C.PAYMENT_MOCK_PAID, C.PAYMENT_REFUNDED]
    assert len(rows) == 2  # exactly one refunded event


# ---------------------------------------------------------------------------
# T-M7-20 / D7 — cancel vs accept race: exactly one wins, state consistent
# ---------------------------------------------------------------------------

def test_m7_20_cancel_accept_race(client, db_session, db_factory, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_PLACED)
    customer_bag = SimpleNamespace(id=world.customer1.id, role=C.ROLE_CUSTOMER)
    owner_bag = SimpleNamespace(id=world.owner1.id, role=C.ROLE_OWNER)
    from app.services import transitions as T

    results: dict[str, str] = {}
    errors: list[BaseException] = []

    def attempt(name: str, fn) -> None:
        s = db_factory.create()
        try:
            try:
                fn(s)
            except ApiError as e:
                # The thread *lost* the race: the CAS matched 0 rows, so the
                # service rejects exactly as it would over HTTP (409
                # INVALID_TRANSITION). That is expected, not a failure.
                if not (e.status_code == 409 and e.code == "INVALID_TRANSITION"):
                    raise
            # Win or lose, re-read the final committed state the way a client
            # would after a 200/409 response.
            s2 = db_factory.create()
            final = s2.get(Order, order.id)
            results[name] = final.status
            s2.close()
        except BaseException as e:  # noqa: BLE001 — surfaced, never swallowed
            errors.append(e)
        finally:
            s.close()

    def do_cancel(s):
        T.cancel_order(s, customer_bag, order.id)  # type: ignore[arg-type]

    def do_accept(s):
        T.accept_order(s, owner_bag, order.id)  # type: ignore[arg-type]

    threads = [threading.Thread(target=attempt, args=("cancel", do_cancel)),
               threading.Thread(target=attempt, args=("accept", do_accept))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors, errors

    db_session.expire_all()
    final = db_session.get(Order, order.id)
    rows = db_session.query(PaymentLedger).filter_by(order_id=order.id).all()
    if final.status == C.ORDER_CANCELLED:
        assert results == {"cancel": C.ORDER_CANCELLED, "accept": C.ORDER_CANCELLED}
        assert final.payment_status == C.PAYMENT_REFUNDED
        assert sorted(x.type for x in rows) == [C.PAYMENT_MOCK_PAID, C.PAYMENT_REFUNDED]
    else:
        assert final.status == C.ORDER_ACCEPTED
        assert final.payment_status == C.PAYMENT_MOCK_PAID
        assert [x.type for x in rows] == [C.PAYMENT_MOCK_PAID]  # no reversal


# ---------------------------------------------------------------------------
# T-M4-16/17 — two-owner / two-partner isolation on lifecycle endpoints
# ---------------------------------------------------------------------------

def test_m4_16_owner_isolation_on_orders(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_READY)
    # owner2 has a valid role, zero access to rest1's orders
    for url, body in [
        (f"/api/v1/orders/{order.id}/accept", None),
        (f"/api/v1/orders/{order.id}/status", {"status": C.ORDER_PREPARING}),
        (f"/api/v1/orders/{order.id}/assign",
         {"delivery_partner_id": world.partner1.id}),
    ]:
        r = client.post(url, headers=bearer(world.tok_owner2), json=body)
        assert r.status_code == 404, url
    # and owner2's dashboard shows none of rest1's orders
    assert client.get("/api/v1/owner/orders",
                      headers=bearer(world.tok_owner2)).json()["total"] == 0
    # owner1's dashboard does show it
    assert client.get("/api/v1/owner/orders",
                      headers=bearer(world.tok_owner1)).json()["total"] == 1
    db_session.expire_all()
    assert db_session.get(Order, order.id).status == C.ORDER_READY  # untouched
