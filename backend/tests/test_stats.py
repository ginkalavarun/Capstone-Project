"""M8 statistics tests (docs/test-plan.md §M8: T-M8-02, T-M8-11 — the D35
metric set) plus the owner-scoping half of T-M4-16 on stats.
"""
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.core import constants as C
from app.db.engine import utcnow
from app.db.models import Order
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
    owner1 = make_user(db_session, "own1@example.org", C.ROLE_OWNER, "Owner 1")
    owner2 = make_user(db_session, "own2@example.org", C.ROLE_OWNER, "Owner 2")
    customer1 = make_user(db_session, "cust1@example.org", C.ROLE_CUSTOMER, "Cust 1")
    partner1 = make_user(db_session, "dp1@example.org", C.ROLE_PARTNER, "Partner 1")
    rest1 = make_restaurant(db_session, owner1, "Alpha", fee=250)
    rest2 = make_restaurant(db_session, owner2, "Beta", fee=350)
    item1 = make_item(db_session, rest1, "Grilled Chicken", 1200)
    item2 = make_item(db_session, rest2, "Beta Roll", 500)
    db_session.commit()
    return SimpleNamespace(
        customer1=customer1, owner1=owner1, owner2=owner2, partner1=partner1,
        rest1=rest1, rest2=rest2, item1=item1, item2=item2,
        tok_customer1=login_token(client, "cust1@example.org"),
        tok_owner1=login_token(client, "own1@example.org"),
        tok_owner2=login_token(client, "own2@example.org"),
        tok_partner1=login_token(client, "dp1@example.org"),
    )


def seed_stats_orders(db_session, world) -> dict[str, Order]:
    """rest1 (fee 250, item 1200 → total 1450 each):

    - o_placed:   PLACED, backdated 40 min (to exercise the date range)
    - o_deliv:    DELIVERED (delivered 5 min ago)
    - o_cancel:   CANCELLED (mock reversal: one refunded ledger event)
    - o_refund:   REFUNDED (delivered 20 min ago, then refunded)

    rest2 (fee 350, item 500): one PLACED order (850) to prove scoping.
    """
    o_placed = make_order(db_session, world.customer1, world.rest1, world.item1,
                          status=C.ORDER_PLACED, age_minutes=40)
    o_deliv = make_order(db_session, world.customer1, world.rest1, world.item1,
                         status=C.ORDER_DELIVERED)
    o_cancel = make_order(db_session, world.customer1, world.rest1, world.item1,
                          status=C.ORDER_CANCELLED)
    o_refund = make_order(db_session, world.customer1, world.rest1, world.item1,
                          status=C.ORDER_REFUNDED, age_minutes=20)
    make_order(db_session, world.customer1, world.rest2, world.item2,
               status=C.ORDER_PLACED, fee=350)  # rest2's actual fee
    return {"placed": o_placed, "deliv": o_deliv, "cancel": o_cancel,
            "refund": o_refund}


def get_stats(client, world, **params):
    return client.get("/api/v1/owner/stats", headers=bearer(world.tok_owner1),
                      params=params or None)


# ---------------------------------------------------------------------------
# T-M8-02 / DASH-02 — own-restaurant stats, filtered, paginated-free
# ---------------------------------------------------------------------------

def test_m8_02_stats_own_restaurant_only(client, db_session, world):
    orders = seed_stats_orders(db_session, world)

    d = get_stats(client, world).json()
    assert d["currency"] == "EUR"
    assert d["placed_order_count"] == 4
    assert d["orders_by_status"] == {
        C.ORDER_PLACED: 1, C.ORDER_ACCEPTED: 0, C.ORDER_PREPARING: 0,
        C.ORDER_READY: 0, C.ORDER_ASSIGNED: 0, C.ORDER_OUT_FOR_DELIVERY: 0,
        C.ORDER_DELIVERED: 1, C.ORDER_CANCELLED: 1, C.ORDER_REFUNDED: 1,
    }
    # rest2's order must not leak in (own restaurant only — T-M4-16 half)
    assert d["gross_mock_paid_cents"] == 4 * 1450  # not 4*1450 + 1350

    # another owner sees their (empty) restaurant, never rest1's numbers
    d2 = client.get("/api/v1/owner/stats", headers=bearer(world.tok_owner2)).json()
    assert d2["placed_order_count"] == 1
    assert d2["orders_by_status"][C.ORDER_PLACED] == 1  # rest2's own order
    assert d2["gross_mock_paid_cents"] == 850  # 500 + 350

    # non-owners → 403
    assert client.get("/api/v1/owner/stats",
                      headers=bearer(world.tok_customer1)).status_code == 403
    assert client.get("/api/v1/owner/stats",
                      headers=bearer(world.tok_partner1)).status_code == 403
    db_session.expire_all()
    assert db_session.get(Order, orders["deliv"].id).status == C.ORDER_DELIVERED


# ---------------------------------------------------------------------------
# T-M8-11 / D35 — exact metric definitions and arithmetic
# ---------------------------------------------------------------------------

def test_m8_11_metric_definitions(client, db_session, world):
    seed_stats_orders(db_session, world)
    d = get_stats(client, world).json()
    gross, refunded, net = (
        d["gross_mock_paid_cents"], d["refunded_cents"], d["net_retained_cents"])
    # every placed order charged 1450 (1200 + 250 fee) → gross 5800
    assert gross == 4 * 1450
    # refunded events: the cancellation reversal + the approved refund
    assert refunded == 2 * 1450
    # exact arithmetic, integer cents (D35: net = gross − refunded)
    assert net == gross - refunded == 2 * 1450
    # delivered count INCLUDES the later-refunded order (D31)
    assert d["delivered_count"] == 2
    assert d["items_sold"] == 4  # one line per order
    assert d["avg_order_value_cents"] == gross // 4 == 1450


def test_m8_11_date_range(client, db_session, world):
    seed_stats_orders(db_session, world)
    cutoff = utcnow() - timedelta(minutes=30)  # excludes the 40-min-old order
    d = get_stats(client, world, date_from=cutoff.isoformat()).json()
    assert d["placed_order_count"] == 3  # the old one is out of range
    assert d["gross_mock_paid_cents"] == 3 * 1450
    assert d["refunded_cents"] == 2 * 1450  # both refunds are recent events
    assert d["net_retained_cents"] == 1 * 1450
    assert d["delivered_count"] == 2  # both deliveries are recent (D31)
    assert d["avg_order_value_cents"] == (3 * 1450) // 3
