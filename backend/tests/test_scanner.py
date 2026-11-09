"""M8 reminder-scanner tests (docs/test-plan.md §M8: T-M8-03…07, D6, BG-01…05).

The scan *logic* is exercised by calling `ReminderScanner.run_scan()` /
`scan_once` directly against a **fake clock** (D6: controllable "now" — no
real 15-minute waits). The lifespan wiring (start with app, stop on
shutdown, fresh session per scan) is tested with a real (1 s) interval and
a genuinely backdated stale order.
"""
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import constants as C
from app.db.engine import utcnow
from app.db.models import ReminderLog
from app.main import create_app
from app.services.reminders import ReminderScanner
from tests.conftest import make_test_settings
from tests.test_lifecycle import (
    bearer,
    make_item,
    make_order,
    make_restaurant,
    make_user,
)
from tests.test_auth import login_token


class FakeClock:
    """The injectable "now" (D6). Starts at the real UTC now; tests
    advance it explicitly — the threshold math is deterministic."""

    def __init__(self):
        self.t = utcnow()

    def __call__(self):
        return self.t

    def advance(self, minutes: float) -> None:
        self.t = self.t + timedelta(minutes=minutes)


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


def _count(db_session, order_id: int) -> int:
    db_session.expire_all()
    return db_session.query(ReminderLog).filter_by(order_id=order_id).count()


# ---------------------------------------------------------------------------
# T-M8-03 / BG-01 — lifecycle: fresh session per scan, clean start/stop
# ---------------------------------------------------------------------------

def test_m8_03_fresh_session_per_scan_and_clean_shutdown(db_factory):
    class CountingFactory:
        """Wraps the real factory and counts `create()` calls — the D1
        "fresh session per scan" property, observable without a mock DB."""

        def __init__(self, inner):
            self._inner = inner
            self.created = 0

        def create(self):
            self.created += 1
            return self._inner.create()

        def get(self):
            return self._inner.get()

    counting = CountingFactory(db_factory)
    scanner = ReminderScanner(counting, interval_seconds=0.2, stale_minutes=15)
    scanner.start()
    assert scanner.running
    time.sleep(0.8)  # several 0.2 s ticks
    created_while_running = counting.created
    assert created_while_running >= 2  # every tick opened its own session
    scanner.stop()
    assert not scanner.running  # the thread joined (clean shutdown, BG-05)
    time.sleep(0.5)
    assert counting.created == created_while_running  # no ticks after stop


def test_m8_03_lifespan_wiring(db_url, db_session, world):
    """The scanner starts with the app (gated by config) and stops when
    the lifespan shuts down; it detects a genuinely stale order within a
    couple of 1 s ticks — no 15-minute wait (the order is backdated)."""
    app = create_app(
        make_test_settings(
            db_url,
            reminder_scanner_enabled=True,
            reminder_interval_seconds=1,
        )
    )
    with TestClient(app):
        scanner = app.state.reminder_scanner
        assert scanner is not None and scanner.running
        # world's data lives in the same DB file; seed a 16-min-old PLACED
        # order (make_order backdates status_updated_at)
        order = make_order(db_session, world.customer1, world.rest1, world.item1,
                           status=C.ORDER_PLACED, age_minutes=16)
        deadline = time.time() + 8
        found = False
        while time.time() < deadline:
            db_session.expire_all()
            if db_session.query(ReminderLog).filter_by(order_id=order.id).count() == 1:
                found = True
                break
            time.sleep(0.25)
        assert found, "the scanner never detected the stale order"
    # after the context exits, the lifespan stopped the scanner
    assert app.state.reminder_scanner is not None
    assert not app.state.reminder_scanner.running


# ---------------------------------------------------------------------------
# T-M8-04 / BG-02 — stale detection: threshold + both states + ineligibles
# ---------------------------------------------------------------------------

def _backdate(order, clock, minutes: float) -> None:
    order.status_updated_at = clock() - timedelta(minutes=minutes)
    order.updated_at = order.status_updated_at
    return order


def test_m8_04_stale_detection(db_session, db_factory, world):
    clock = FakeClock()
    scanner = ReminderScanner(db_factory, interval_seconds=60, stale_minutes=15,
                              clock=clock)

    below = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_PLACED)
    _backdate(below, clock, 14.9)  # 14m59s — just under
    exact = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_ACCEPTED)
    _backdate(exact, clock, 15.0)  # exactly 15:00 — NOT "more than 15 minutes"
    over = make_order(db_session, world.customer1, world.rest1, world.item1,
                      status=C.ORDER_PLACED)
    _backdate(over, clock, 15.02)  # 15m01s — over the threshold
    prepared = make_order(db_session, world.customer1, world.rest1, world.item1,
                          status=C.ORDER_READY)
    _backdate(prepared, clock, 45.0)  # stale, but READY is not eligible
    db_session.commit()

    created = scanner.run_scan()

    assert created == 1  # only `over`
    db_session.expire_all()
    assert _count(db_session, over.id) == 1
    row = db_session.query(ReminderLog).filter_by(order_id=over.id).one()
    assert row.status_at_reminder == C.ORDER_PLACED
    assert row.detected_at == clock()  # stamped with the scan's "now" (D33)
    assert row.resolved is False
    assert _count(db_session, below.id) == 0
    assert _count(db_session, exact.id) == 0
    assert _count(db_session, prepared.id) == 0

    # the ACCEPTED side: both eligible states are detected
    _backdate(exact, clock, 20.0)
    db_session.commit()
    assert scanner.run_scan() == 1
    db_session.expire_all()
    row2 = db_session.query(ReminderLog).filter_by(order_id=exact.id).one()
    assert row2.status_at_reminder == C.ORDER_ACCEPTED


# ---------------------------------------------------------------------------
# T-M8-05 / BG-03 / D20 — dedupe per episode, resolve on progress, new
# episode gets a new reminder
# ---------------------------------------------------------------------------

def test_m8_05_dedupe_resolve_new_episode(db_session, db_factory, world):
    clock = FakeClock()
    scanner = ReminderScanner(db_factory, interval_seconds=60, stale_minutes=15,
                              clock=clock)

    o = make_order(db_session, world.customer1, world.rest1, world.item1,
                   status=C.ORDER_PLACED)
    _backdate(o, clock, 20.0)
    db_session.commit()

    assert scanner.run_scan() == 1
    assert _count(db_session, o.id) == 1
    # second tick, same episode, order unchanged → nothing new (D6: "one
    # reminder per status episode, not per tick")
    assert scanner.run_scan() == 0
    assert _count(db_session, o.id) == 1

    # the order leaves PLACED (owner progress — the machine itself is
    # proven in batch 5; here we only move the fixture row) → the episode
    # ended: the reminder is resolved, not duplicated
    o.status = C.ORDER_READY
    o.status_updated_at = clock()
    db_session.commit()
    assert scanner.run_scan() == 0
    db_session.expire_all()
    row = db_session.query(ReminderLog).filter_by(order_id=o.id).one()
    assert row.resolved is True
    assert row.resolved_at == clock()  # stamped with the resolving "now"
    assert _count(db_session, o.id) == 1  # still exactly one row

    # a *different* status episode on another order is reminded afresh
    o2 = make_order(db_session, world.customer2, world.rest1, world.item1,
                    status=C.ORDER_ACCEPTED)
    _backdate(o2, clock, 30.0)
    db_session.commit()
    assert scanner.run_scan() == 1
    db_session.expire_all()
    row2 = db_session.query(ReminderLog).filter_by(order_id=o2.id).one()
    assert row2.status_at_reminder == C.ORDER_ACCEPTED and row2.resolved is False


# ---------------------------------------------------------------------------
# T-M8-06 / BG-04, T-M4-16 — visibility: own restaurant only
# ---------------------------------------------------------------------------

def test_m8_06_owner_visibility(client, db_session, world):
    stale = make_order(db_session, world.customer1, world.rest1, world.item1,
                       status=C.ORDER_PLACED)
    db_session.add(ReminderLog(
        order_id=stale.id, status_at_reminder=C.ORDER_PLACED,
        detected_at=utcnow(), resolved=False,
    ))
    # a resolved reminder for the same restaurant is hidden from the list
    done = make_order(db_session, world.customer1, world.rest1, world.item1,
                      status=C.ORDER_PREPARING)
    db_session.add(ReminderLog(
        order_id=done.id, status_at_reminder=C.ORDER_PLACED,
        detected_at=utcnow(), resolved=True, resolved_at=utcnow(),
    ))
    db_session.commit()

    d = client.get("/api/v1/owner/reminders", headers=bearer(world.tok_owner1)).json()
    assert d["total"] == 1  # the open one only
    item = d["items"][0]
    assert item["order_id"] == stale.id
    assert item["status_at_reminder"] == C.ORDER_PLACED
    assert item["order_status"] == C.ORDER_PLACED
    assert item["resolved"] is False
    assert item["order_total_cents"] == 1200 + 250

    # another owner: 200 but their own (empty) list — never foreign rows
    d2 = client.get("/api/v1/owner/reminders", headers=bearer(world.tok_owner2))
    assert d2.status_code == 200 and d2.json()["total"] == 0
    # non-owners → 403
    assert client.get("/api/v1/owner/reminders",
                      headers=bearer(world.tok_customer1)).status_code == 403
    assert client.get("/api/v1/owner/reminders",
                      headers=bearer(world.tok_partner1)).status_code == 403


# ---------------------------------------------------------------------------
# T-M8-07 / BG-05 — a failed scan is logged and the loop continues
# ---------------------------------------------------------------------------

def test_m8_07_scan_errors_never_stop_the_loop(db_factory):
    class FlakyFactory:
        """Fails exactly once (the first session), then behaves."""

        def __init__(self, inner):
            self._inner = inner
            self.calls = 0

        def create(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("simulated scan failure")
            return self._inner.create()

    flaky = FlakyFactory(db_factory)
    scanner = ReminderScanner(flaky, interval_seconds=0.2, stale_minutes=15)
    scanner.start()
    time.sleep(1.0)  # several ticks: one failed + some successful
    assert scanner.errors >= 1  # the failure was recorded (and logged)
    assert scanner.scans >= 1  # …and the loop recovered
    assert scanner.running  # …without crashing the app
    scanner.stop()
    assert not scanner.running
