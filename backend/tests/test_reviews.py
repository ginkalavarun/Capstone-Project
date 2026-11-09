"""M9 review tests (docs/test-plan.md §M9, REV-01…05, D31).

Covers T-M9-08, T-M9-09, T-M9-10 (the DB constraint), T-M9-12 plus the
authorization/eligibility edges of the review endpoint.
"""
import pytest
from types import SimpleNamespace

from sqlalchemy.exc import IntegrityError

from app.core import constants as C
from app.db.models import Order, RefundRequest, Review
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
    rest1 = make_restaurant(db_session, owner1, "Alpha", fee=250)
    item1 = make_item(db_session, rest1, "Grilled Chicken", 1200)
    db_session.commit()
    return SimpleNamespace(
        customer1=customer1, customer2=customer2, owner1=owner1,
        rest1=rest1, item1=item1,
        tok_customer1=login_token(client, "cust1@example.org"),
        tok_customer2=login_token(client, "cust2@example.org"),
        tok_owner1=login_token(client, "own1@example.org"),
    )


# ---------------------------------------------------------------------------
# T-M9-08 / REV-01 — review after delivery
# ---------------------------------------------------------------------------

def test_m9_08_review_after_delivered(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_DELIVERED)
    r = client.post(f"/api/v1/orders/{order.id}/review",
                    headers=bearer(world.tok_customer1),
                    json={"rating": 4, "comment": "Great, slightly late."})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["rating"] == 4 and body["order_id"] == order.id
    # not-yet-delivered orders are ineligible (REV-01)
    for from_status in (C.ORDER_PLACED, C.ORDER_OUT_FOR_DELIVERY, C.ORDER_CANCELLED):
        o = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=from_status)
        rr = client.post(f"/api/v1/orders/{o.id}/review",
                         headers=bearer(world.tok_customer1),
                         json={"rating": 5})
        assert rr.status_code == 409, (from_status, rr.text)
        assert rr.json()["code"] == "ORDER_INELIGIBLE"
    # rating bounds (pydantic: outside 1–5 is a 422, not a business error)
    d = make_order(db_session, world.customer1, world.rest1, world.item1,
                   status=C.ORDER_DELIVERED)
    for bad in (0, 6):
        assert client.post(f"/api/v1/orders/{d.id}/review",
                           headers=bearer(world.tok_customer1),
                           json={"rating": bad}).status_code == 422
    # someone else's order → 404 (existence hidden — AUTHZ-06)
    r = client.post(f"/api/v1/orders/{order.id}/review",
                    headers=bearer(world.tok_customer2),
                    json={"rating": 5})
    assert r.status_code == 404
    # owner/partner roles cannot review a customer order
    assert client.post(f"/api/v1/orders/{order.id}/review",
                       headers=bearer(world.tok_owner1),
                       json={"rating": 5}).status_code == 403


# ---------------------------------------------------------------------------
# T-M9-09 / REV-02 — one review per order
# ---------------------------------------------------------------------------

def test_m9_09_one_review(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_DELIVERED)
    h = bearer(world.tok_customer1)
    assert client.post(f"/api/v1/orders/{order.id}/review",
                       headers=h, json={"rating": 5}).status_code == 201
    r = client.post(f"/api/v1/orders/{order.id}/review",
                    headers=h, json={"rating": 1, "comment": "changed my mind"})
    assert r.status_code == 409 and r.json()["code"] == "REVIEW_EXISTS"
    db_session.expire_all()
    assert db_session.query(Review).filter_by(order_id=order.id).count() == 1


# ---------------------------------------------------------------------------
# T-M9-10 / REV-03 — database backstop
# ---------------------------------------------------------------------------

def test_m9_10_db_unique_constraint(db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_DELIVERED)
    db_session.add(Review(order_id=order.id, customer_id=world.customer1.id,
                          rating=5, comment=None))
    db_session.commit()
    with pytest.raises(IntegrityError):
        db_session.add(Review(order_id=order.id, customer_id=world.customer1.id,
                              rating=4, comment="duplicate"))
        db_session.commit()
    db_session.rollback()
    db_session.expire_all()
    assert db_session.query(Review).filter_by(order_id=order.id).count() == 1


# ---------------------------------------------------------------------------
# T-M9-12 / D31, REV-05 — review survives a later refund
# ---------------------------------------------------------------------------

def test_m9_12_review_after_later_refund(client, db_session, world):
    order = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_DELIVERED)
    db_session.add(RefundRequest(order_id=order.id, status=C.REFUND_PENDING,
                                 reason="cold"))
    db_session.commit()
    assert client.post(f"/api/v1/orders/{order.id}/refund/approve",
                       headers=bearer(world.tok_owner1)).status_code == 200
    # the order is now REFUNDED — but delivered_at is set, so the review
    # must still be possible (D31: eligibility = actually delivered)
    r = client.post(f"/api/v1/orders/{order.id}/review",
                    headers=bearer(world.tok_customer1),
                    json={"rating": 3, "comment": "food was fine, still refunded"})
    assert r.status_code == 201, r.text
    assert r.json()["rating"] == 3
    db_session.expire_all()
    assert db_session.get(Order, order.id).status == C.ORDER_REFUNDED
    assert db_session.query(Review).filter_by(order_id=order.id).count() == 1
