"""M9 refund tests + the refund half of the stats adjacency (docs/test-plan.md §M9).

Covers T-M9-01…07, T-M9-13, T-M9-14 plus a threaded double-approval race
(a strengthening of T-M9-04's "double-approve" semantics under concurrency).
The DB backstop for the *review* constraint (T-M9-10) lives in
test_reviews.py; the D28 backstop (`uq_refunds_order`) is asserted in
test_m9_03.
"""
import threading
from types import SimpleNamespace

import pytest

from app.core import constants as C
from app.db.models import Order, PaymentLedger, RefundRequest
from app.services.refunds import approve_refund
from tests.test_lifecycle import (
    bearer,
    make_item,
    make_order,
    make_restaurant,
    make_user,
)
from tests.test_auth import login_token


@pytest.fixture()
def world(client, db_session, db_factory):
    customer1 = make_user(db_session, "cust1@example.org", C.ROLE_CUSTOMER, "Cust 1")
    customer2 = make_user(db_session, "cust2@example.org", C.ROLE_CUSTOMER, "Cust 2")
    owner1 = make_user(db_session, "own1@example.org", C.ROLE_OWNER, "Owner 1")
    owner2 = make_user(db_session, "own2@example.org", C.ROLE_OWNER, "Owner 2")
    partner1 = make_user(db_session, "dp1@example.org", C.ROLE_PARTNER, "Partner 1")
    rest1 = make_restaurant(db_session, owner1, "Alpha", fee=250)
    rest2 = make_restaurant(db_session, owner2, "Beta", fee=350)
    item1 = make_item(db_session, rest1, "Grilled Chicken", 1200)
    db_session.commit()
    return SimpleNamespace(
        customer1=customer1, customer2=customer2, owner1=owner1, owner2=owner2,
        partner1=partner1, rest1=rest1, rest2=rest2, item1=item1,
        tok_customer1=login_token(client, "cust1@example.org"),
        tok_customer2=login_token(client, "cust2@example.org"),
        tok_owner1=login_token(client, "own1@example.org"),
        tok_owner2=login_token(client, "own2@example.org"),
        tok_partner1=login_token(client, "dp1@example.org"),
    )


# ---------------------------------------------------------------------------
# T-M9-01 / REF-01 — request after delivery
# ---------------------------------------------------------------------------

def test_m9_01_request_after_delivered(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_DELIVERED)
    r = client.post(f"/api/v1/orders/{order.id}/refund-request",
                    headers=bearer(world.tok_customer1),
                    json={"reason": "Food arrived cold."})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == C.REFUND_PENDING
    assert body["order_id"] == order.id
    assert body["reason"] == "Food arrived cold."
    db_session.expire_all()
    assert db_session.query(RefundRequest).filter_by(order_id=order.id).count() == 1
    # blank reason is rejected by validation (REF-01: required reason)
    other = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_DELIVERED)
    r = client.post(f"/api/v1/orders/{other.id}/refund-request",
                    headers=bearer(world.tok_customer1), json={"reason": "   "})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# T-M9-02 / REF-01 — not before delivery
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("from_status", [
    C.ORDER_PLACED, C.ORDER_ACCEPTED, C.ORDER_PREPARING, C.ORDER_READY,
    C.ORDER_ASSIGNED, C.ORDER_OUT_FOR_DELIVERY, C.ORDER_CANCELLED,
    C.ORDER_REFUNDED,
])
def test_m9_02_not_before_delivery(client, db_session, world, from_status):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=from_status)
    r = client.post(f"/api/v1/orders/{order.id}/refund-request",
                    headers=bearer(world.tok_customer1),
                    json={"reason": "why not"})
    assert r.status_code == 409, (from_status, r.text)
    assert r.json()["code"] == "ORDER_INELIGIBLE"
    db_session.expire_all()
    assert db_session.query(RefundRequest).filter_by(order_id=order.id).count() == 0


# ---------------------------------------------------------------------------
# T-M9-03 / REF-02, D28 — one request per order, permanently
# ---------------------------------------------------------------------------

def test_m9_03_one_request_only(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_DELIVERED)
    h = bearer(world.tok_customer1)
    assert client.post(f"/api/v1/orders/{order.id}/refund-request",
                       headers=h, json={"reason": "first"}).status_code == 201
    r = client.post(f"/api/v1/orders/{order.id}/refund-request",
                    headers=h, json={"reason": "second"})
    assert r.status_code == 409 and r.json()["code"] == "REFUND_REQUEST_EXISTS"
    db_session.expire_all()
    assert db_session.query(RefundRequest).filter_by(order_id=order.id).count() == 1


# ---------------------------------------------------------------------------
# T-M9-04 / REF-03, REF-04, D30 — approve: atomic, idempotent, one ledger row
# ---------------------------------------------------------------------------

def _pending_delivered(db_session, world, **kw) -> Order:
    """A DELIVERED order (seeded straight in the DB — checkout is proven in
    batch 4) plus a pending refund request, so the decision tests don't pay
    the HTTP round-trip for the request half."""
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_DELIVERED, **kw)
    db_session.add(RefundRequest(order_id=order.id, status=C.REFUND_PENDING,
                                 reason="cold"))
    db_session.commit()
    return order


def test_m9_04_approve(client, db_session, world):
    order = _pending_delivered(db_session, world)
    r = client.post(f"/api/v1/orders/{order.id}/refund/approve",
                    headers=bearer(world.tok_owner1))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == C.ORDER_REFUNDED
    assert r.json()["payment_status"] == C.PAYMENT_REFUNDED
    assert r.json()["refund_status"] == C.REFUND_APPROVED
    db_session.expire_all()
    rows = db_session.query(PaymentLedger).filter_by(order_id=order.id).all()
    assert sorted(x.type for x in rows) == [C.PAYMENT_MOCK_PAID, C.PAYMENT_REFUNDED]
    # double-approval: 200 no-op, still exactly one refunded row (REF-04)
    r = client.post(f"/api/v1/orders/{order.id}/refund/approve",
                    headers=bearer(world.tok_owner1))
    assert r.status_code == 200 and r.json()["status"] == C.ORDER_REFUNDED
    db_session.expire_all()
    rows = db_session.query(PaymentLedger).filter_by(order_id=order.id).all()
    assert [x.type for x in rows] == [C.PAYMENT_MOCK_PAID, C.PAYMENT_REFUNDED]
    assert len(rows) == 2


def test_m9_04_approve_race(client, db_session, db_factory, world):
    """T-M9-04 under concurrency: two simultaneous approvals → exactly one
    `refunded` ledger row, order REFUNDED, request approved, no errors."""
    order = _pending_delivered(db_session, world)
    owner_bag = SimpleNamespace(id=world.owner1.id, role=C.ROLE_OWNER)

    results: list[int] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def attempt() -> None:
        s = db_factory.create()
        try:
            out = approve_refund(s, owner_bag, order.id)  # type: ignore[arg-type]
            s2 = db_factory.create()
            final = s2.get(Order, order.id)
            with lock:
                results.append(200 if final.status == C.ORDER_REFUNDED else -1)
            s2.close()
        except BaseException as e:  # noqa: BLE001 — surfaced, never swallowed
            with lock:
                errors.append(e)
        finally:
            s.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors, errors
    assert results == [200, 200]  # both callers end on the consistent state
    db_session.expire_all()
    final = db_session.get(Order, order.id)
    assert final.status == C.ORDER_REFUNDED
    assert final.payment_status == C.PAYMENT_REFUNDED
    rows = db_session.query(PaymentLedger).filter_by(order_id=order.id).all()
    assert [x.type for x in rows] == [C.PAYMENT_MOCK_PAID, C.PAYMENT_REFUNDED]
    assert db_session.query(RefundRequest).filter_by(order_id=order.id).one().status == C.REFUND_APPROVED


# ---------------------------------------------------------------------------
# T-M9-05 / REF-03, T-M4-16 — approve authorization
# ---------------------------------------------------------------------------

def test_m9_05_approve_authorization(client, db_session, world):
    order = _pending_delivered(db_session, world)
    url = f"/api/v1/orders/{order.id}/refund/approve"
    # another owner → 404 (T-M4-16 half: valid role, foreign resource)
    r = client.post(url, headers=bearer(world.tok_owner2))
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"
    # customer / partner → 403
    assert client.post(url, headers=bearer(world.tok_customer1)).status_code == 403
    assert client.post(url, headers=bearer(world.tok_partner1)).status_code == 403
    # unknown order → 404
    assert client.post("/api/v1/orders/999999/refund/approve",
                       headers=bearer(world.tok_owner1)).status_code == 404
    # a DELIVERED order with *no* request → 404 (existence of the request hidden)
    bare = make_order(db_session, world.customer1, world.rest1, world.item1,
                      status=C.ORDER_DELIVERED)
    assert client.post(f"/api/v1/orders/{bare.id}/refund/approve",
                       headers=bearer(world.tok_owner1)).status_code == 404
    db_session.expire_all()
    assert db_session.get(Order, order.id).status == C.ORDER_DELIVERED  # untouched


# ---------------------------------------------------------------------------
# T-M9-06 / REF-05, D28 — reject
# ---------------------------------------------------------------------------

def test_m9_06_reject(client, db_session, world):
    order = _pending_delivered(db_session, world)
    r = client.post(f"/api/v1/orders/{order.id}/refund/reject",
                    headers=bearer(world.tok_owner1))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == C.ORDER_DELIVERED      # unchanged (REF-05)
    assert r.json()["payment_status"] == C.PAYMENT_MOCK_PAID
    assert r.json()["refund_status"] == C.REFUND_REJECTED
    db_session.expire_all()
    req = db_session.query(RefundRequest).filter_by(order_id=order.id).one()
    assert req.status == C.REFUND_REJECTED and req.decided_by == world.owner1.id
    assert db_session.query(PaymentLedger).filter_by(order_id=order.id).count() == 1
    # double-decision: both paths 409 (REF-02/D28)
    assert client.post(f"/api/v1/orders/{order.id}/refund/approve",
                       headers=bearer(world.tok_owner1)).status_code == 409
    assert client.post(f"/api/v1/orders/{order.id}/refund/reject",
                       headers=bearer(world.tok_owner1)).status_code == 409
    db_session.expire_all()
    assert db_session.get(Order, order.id).status == C.ORDER_DELIVERED


# ---------------------------------------------------------------------------
# T-M9-07 / REF-06 — customer sees payment + refund status
# ---------------------------------------------------------------------------

def test_m9_07_customer_sees_state(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_DELIVERED)
    h = bearer(world.tok_customer1)
    d = client.get(f"/api/v1/orders/{order.id}", headers=h).json()
    assert d["payment_status"] == C.PAYMENT_MOCK_PAID
    assert d["refund_status"] is None
    client.post(f"/api/v1/orders/{order.id}/refund-request", headers=h,
                json={"reason": "cold"})
    assert client.get(f"/api/v1/orders/{order.id}", headers=h).json()["refund_status"] == C.REFUND_PENDING
    client.post(f"/api/v1/orders/{order.id}/refund/approve",
                headers=bearer(world.tok_owner1))
    d = client.get(f"/api/v1/orders/{order.id}", headers=h).json()
    assert d["status"] == C.ORDER_REFUNDED
    assert d["payment_status"] == C.PAYMENT_REFUNDED
    assert d["refund_status"] == C.REFUND_APPROVED


# ---------------------------------------------------------------------------
# T-M9-13 / D28 — no re-request after rejection
# ---------------------------------------------------------------------------

def test_m9_13_no_rerequest_after_rejection(client, db_session, world):
    order = _pending_delivered(db_session, world)
    client.post(f"/api/v1/orders/{order.id}/refund/reject",
                headers=bearer(world.tok_owner1))
    r = client.post(f"/api/v1/orders/{order.id}/refund-request",
                    headers=bearer(world.tok_customer1),
                    json={"reason": "actually it was bad"})
    assert r.status_code == 409 and r.json()["code"] == "REFUND_REQUEST_EXISTS"
    db_session.expire_all()
    assert db_session.query(RefundRequest).filter_by(order_id=order.id).count() == 1
    assert db_session.query(RefundRequest).filter_by(order_id=order.id).one().status == C.REFUND_REJECTED


# ---------------------------------------------------------------------------
# T-M9-14 / D29 — cancellation is not a refund request
# ---------------------------------------------------------------------------

def test_m9_14_cancellation_is_not_a_refund_request(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_PLACED)
    assert client.post(f"/api/v1/orders/{order.id}/cancel",
                       headers=bearer(world.tok_customer1)).status_code == 200
    db_session.expire_all()
    assert db_session.query(RefundRequest).filter_by(order_id=order.id).count() == 0
    rows = db_session.query(PaymentLedger).filter_by(order_id=order.id).all()
    assert [x.type for x in rows] == [C.PAYMENT_MOCK_PAID, C.PAYMENT_REFUNDED]
    # and the customer cannot now "request" a refund of the cancelled order
    r = client.post(f"/api/v1/orders/{order.id}/refund-request",
                    headers=bearer(world.tok_customer1),
                    json={"reason": "give me my money"})
    assert r.status_code == 409 and r.json()["code"] == "ORDER_INELIGIBLE"
