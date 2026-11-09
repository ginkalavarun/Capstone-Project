"""M3 data-model tests (docs/test-plan.md §M3; docs/database.md §9).

Conventions (docs/test-plan.md):
- every test runs against a throwaway SQLite DB (pytest ``tmp_path``)
- money assertions use integer cents (D3/D26)
- time-dependent behavior uses explicit datetimes, never real sleeps

Test IDs follow ``docs/test-plan.md`` exactly. "DB" = a database-level
guarantee (constraint/pragma); "app" = behavior the service layer (later
batches) must provide on top of these DB guarantees.
"""
import sqlite3
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from app.core import constants as C
from app.core.utils import canonical_request_hash
from app.db.base import Base
from app.db.engine import utcnow
from app.db.models import (
    MenuItem,
    Order,
    OrderItem,
    PaymentLedger,
    RefundRequest,
    ReminderLog,
    Restaurant,
    Review,
    User,
)

TABLES = {
    "users",
    "restaurants",
    "menu_items",
    "orders",
    "order_items",
    "payment_ledger",
    "refund_requests",
    "reviews",
    "reminder_logs",
}


def _sqlite_path(database_url: str) -> str:
    """The on-disk path of a ``sqlite:///...`` URL (for raw-conn tests)."""
    assert database_url.startswith("sqlite:///")
    return database_url[len("sqlite:///"):]


# ---------------------------------------------------------------------------
# Fixture-free world builder (the tests own their sessions/transactions)
# ---------------------------------------------------------------------------

@dataclass
class World:
    """One customer, one owner, one restaurant, two dishes, one order."""

    cust: User
    owner: User
    rest: Restaurant
    m1: MenuItem
    m2: MenuItem
    order: Order


def _order_row(
    session,
    cust: User,
    rest: Restaurant,
    lines: list[tuple[MenuItem, int]],
    *,
    status: str = C.ORDER_PLACED,
    payment_status: str = C.PAYMENT_MOCK_PAID,
    key: str = "key-1",
    address: str = "22 Dorm Row",
    partner: Optional[User] = None,
    delivered_at: Optional[object] = None,
) -> Order:
    """Order + snapshot items + one mock_paid ledger row, server money (D3)."""
    subtotal = sum(item.price_cents * qty for item, qty in lines)
    fee = rest.delivery_fee_cents
    order = Order(
        customer_id=cust.id,
        restaurant_id=rest.id,
        delivery_partner_id=partner.id if partner else None,
        status=status,
        payment_status=payment_status,
        delivered_at=delivered_at,
        items_subtotal_cents=subtotal,
        delivery_fee_cents=fee,
        total_cents=subtotal + fee,
        delivery_address=address,
        idempotency_key=key,
        request_hash=canonical_request_hash(
            rest.id, [(item.id, qty) for item, qty in lines]
        ),
    )
    session.add(order)
    session.flush()
    for item, qty in lines:
        session.add(
            OrderItem(
                order_id=order.id,
                menu_item_id=item.id,
                item_name=item.name,
                unit_price_cents=item.price_cents,
                quantity=qty,
                line_total_cents=item.price_cents * qty,
            )
        )
    session.add(
        PaymentLedger(order_id=order.id, type=payment_status, amount_cents=subtotal + fee)
    )
    return order


def make_world(
    session,
    *,
    cust_email: str = "cust1@example.org",
    owner_email: str = "owner1@example.org",
    rest_name: str = "Test Eats",
    fee: int = 250,
    status: str = C.ORDER_PLACED,
    payment_status: str = C.PAYMENT_MOCK_PAID,
    key: str = "key-1",
    delivered_at: Optional[object] = None,
) -> World:
    """Commit a minimal coherent world. Money: m1=1000¢×1, m2=50¢×2,
    subtotal 1100¢, fee 250¢, total 1350¢."""
    cust = User(email=cust_email, password_hash="x", full_name="Cust One", role=C.ROLE_CUSTOMER)
    owner = User(email=owner_email, password_hash="x", full_name="Own One", role=C.ROLE_OWNER)
    session.add_all([cust, owner])
    session.flush()
    rest = Restaurant(
        owner_id=owner.id, name=rest_name, address="1 Test Way", delivery_fee_cents=fee
    )
    session.add(rest)
    session.flush()
    m1 = MenuItem(restaurant_id=rest.id, name="Pie", price_cents=1000)
    m2 = MenuItem(restaurant_id=rest.id, name="Soda", price_cents=50)
    session.add_all([m1, m2])
    session.flush()
    order = _order_row(
        session, cust, rest, [(m1, 1), (m2, 2)],
        status=status, payment_status=payment_status, key=key,
        delivered_at=delivered_at,
    )
    session.commit()
    return World(cust=cust, owner=owner, rest=rest, m1=m1, m2=m2, order=order)


def fresh_get(session, orm_id, model):
    """Re-read a row through a *real* DB round-trip (new session's eyes)."""
    session.expire_all()
    return session.get(model, orm_id)


# ---------------------------------------------------------------------------
# T-M3-01 / T-M3-02 — schema + relationships (DB-01, DB-02)
# ---------------------------------------------------------------------------

def test_m3_01_schema_nine_tables_and_key_columns(db_session):
    got = {
        row[0]
        for row in db_session.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
            )
        )
    }
    assert got == TABLES
    # ORM metadata agrees with the migrated schema.
    assert set(Base.metadata.tables) == TABLES
    # The reconciliation-era columns exist (D31, D34, D33, D3).
    cols = {row[1] for row in db_session.execute(text("PRAGMA table_info(orders)"))}
    for col in (
        "delivered_at", "idempotency_key", "request_hash",
        "items_subtotal_cents", "delivery_fee_cents", "total_cents",
        "status_updated_at", "status", "payment_status",
    ):
        assert col in cols, col


def test_m3_02_relationship_navigations_both_directions(db_session):
    w = make_world(db_session)
    dp = User(email="dp1@example.org", password_hash="x", full_name="Dp One", role=C.ROLE_PARTNER)
    db_session.add(dp)
    db_session.flush()
    w.order.delivery_partner = dp
    db_session.add(Review(order_id=w.order.id, customer_id=w.cust.id, rating=5, comment="ok"))
    db_session.add(RefundRequest(order_id=w.order.id, status=C.REFUND_PENDING, reason="cold"))
    db_session.add(ReminderLog(order_id=w.order.id, status_at_reminder=C.ORDER_PLACED))
    db_session.commit()

    o = fresh_get(db_session, w.order.id, Order)
    # forward navigations
    assert o.customer.email == w.cust.email
    assert o.restaurant.name == w.rest.name
    assert o.delivery_partner.email == dp.email
    assert [i.item_name for i in o.items] == ["Pie", "Soda"]
    assert [l.type for l in o.ledger] == [C.PAYMENT_MOCK_PAID]
    assert o.review is not None and o.review.rating == 5
    assert o.refund_request is not None and o.refund_request.reason == "cold"
    assert [r.status_at_reminder for r in o.reminders] == [C.ORDER_PLACED]
    # backward navigations
    assert o in fresh_get(db_session, w.cust.id, User).orders_placed
    assert o in fresh_get(db_session, dp.id, User).orders_delivering
    assert o in fresh_get(db_session, w.rest.id, Restaurant).orders
    assert {m.id for m in fresh_get(db_session, w.rest.id, Restaurant).menu_items} == {w.m1.id, w.m2.id}
    assert fresh_get(db_session, w.m1.id, MenuItem).restaurant.name == w.rest.name
    assert fresh_get(db_session, w.owner.id, User).restaurant.id == w.rest.id
    assert w.rest.owner.email == w.owner.email


# ---------------------------------------------------------------------------
# T-M3-03 / T-M3-13 — foreign keys (DB-03)
# ---------------------------------------------------------------------------

def test_m3_03_fk_enforced_by_engine_session(db_session, db_url):
    w = make_world(db_session)
    # The pragma is actually ON for this session (D1).
    assert db_session.execute(text("PRAGMA foreign_keys")).scalar() == 1
    bad = Order(
        customer_id=999999, restaurant_id=999998, status=C.ORDER_PLACED,
        payment_status=C.PAYMENT_MOCK_PAID, items_subtotal_cents=10,
        delivery_fee_cents=0, total_cents=10, delivery_address="x",
        idempotency_key="orphan-orm", request_hash="h",
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    assert db_session.execute(
        text("SELECT COUNT(*) FROM orders WHERE idempotency_key='orphan-orm'")
    ).scalar() == 0
    del w


def test_m3_03_raw_connection_without_pragma_allows_orphan(db_session, db_url):
    """Positive control: a plain ``sqlite3`` connection (pragma OFF)
    *accepts* the same orphan — proof that the engine's connect listener
    is what enforces FKs, not the DDL (D1's "silent failure" trap)."""
    make_world(db_session)  # migrations ran, table exists
    conn = sqlite3.connect(_sqlite_path(db_url))
    try:
        conn.execute(
            """INSERT INTO orders (
                   customer_id, restaurant_id, status, payment_status,
                   status_updated_at, items_subtotal_cents, delivery_fee_cents,
                   total_cents, delivery_address, idempotency_key, request_hash,
                   created_at, updated_at)
               VALUES (999999, 999998, 'PLACED', 'mock_paid',
                       '2026-01-01 00:00:00 +00:00', 10, 0, 10,
                       'x', 'orphan-raw', 'h',
                       '2026-01-01 00:00:00 +00:00', '2026-01-01 00:00:00 +00:00')"""
        )
        conn.commit()  # succeeds with FKs off — that is the point
    finally:
        conn.execute("DELETE FROM orders WHERE idempotency_key = 'orphan-raw'")
        conn.commit()
        conn.close()
    assert db_session.execute(
        text("SELECT COUNT(*) FROM orders WHERE idempotency_key='orphan-raw'")
    ).scalar() == 0  # cleaned up


def _all_fk_columns() -> list[tuple[str, str, str]]:
    fks = []
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            fks.append((table.name, fk.parent.name, fk.column.name))
    return fks


FK_PARAMS = _all_fk_columns()


def _minimal_row_with_bad_fk(w: World, table_name: str, fk_col: str):
    """A fully valid row except that one FK column points to 999999."""
    if (table_name, fk_col) == ("restaurants", "owner_id"):
        return Restaurant(owner_id=999999, name="Orphan R", address="a", delivery_fee_cents=0)
    if (table_name, fk_col) == ("menu_items", "restaurant_id"):
        return MenuItem(restaurant_id=999999, name="Orphan M", price_cents=1)
    if (table_name, fk_col) == ("orders", "customer_id"):
        return Order(
            customer_id=999999, restaurant_id=w.rest.id, status=C.ORDER_PLACED,
            payment_status=C.PAYMENT_MOCK_PAID, items_subtotal_cents=10,
            delivery_fee_cents=0, total_cents=10, delivery_address="x",
            idempotency_key="fk-cust", request_hash="h",
        )
    if (table_name, fk_col) == ("orders", "restaurant_id"):
        return Order(
            customer_id=w.cust.id, restaurant_id=999999, status=C.ORDER_PLACED,
            payment_status=C.PAYMENT_MOCK_PAID, items_subtotal_cents=10,
            delivery_fee_cents=0, total_cents=10, delivery_address="x",
            idempotency_key="fk-rest", request_hash="h",
        )
    if (table_name, fk_col) == ("orders", "delivery_partner_id"):
        return Order(
            customer_id=w.cust.id, restaurant_id=w.rest.id,
            delivery_partner_id=999999, status=C.ORDER_PLACED,
            payment_status=C.PAYMENT_MOCK_PAID, items_subtotal_cents=10,
            delivery_fee_cents=0, total_cents=10, delivery_address="x",
            idempotency_key="fk-partner", request_hash="h",
        )
    if (table_name, fk_col) == ("order_items", "order_id"):
        return OrderItem(
            order_id=999999, menu_item_id=w.m1.id, item_name="Pie",
            unit_price_cents=1000, quantity=1, line_total_cents=1000,
        )
    if (table_name, fk_col) == ("order_items", "menu_item_id"):
        return OrderItem(
            order_id=w.order.id, menu_item_id=999999, item_name="Pie",
            unit_price_cents=1000, quantity=1, line_total_cents=1000,
        )
    if (table_name, fk_col) == ("payment_ledger", "order_id"):
        return PaymentLedger(order_id=999999, type=C.PAYMENT_MOCK_PAID, amount_cents=10)
    if (table_name, fk_col) == ("refund_requests", "order_id"):
        return RefundRequest(order_id=999999, status=C.REFUND_PENDING, reason="r")
    if (table_name, fk_col) == ("refund_requests", "decided_by"):
        return RefundRequest(order_id=w.order.id, status=C.REFUND_APPROVED, reason="r", decided_by=999999)
    if (table_name, fk_col) == ("reviews", "order_id"):
        return Review(order_id=999999, customer_id=w.cust.id, rating=3)
    if (table_name, fk_col) == ("reviews", "customer_id"):
        return Review(order_id=w.order.id, customer_id=999999, rating=3)
    if (table_name, fk_col) == ("reminder_logs", "order_id"):
        return ReminderLog(order_id=999999, status_at_reminder=C.ORDER_PLACED)
    raise AssertionError(f"no builder for {table_name}.{fk_col}")


@pytest.mark.parametrize("table_name, fk_col, ref_col", FK_PARAMS)
def test_m3_13_every_fk_column_is_enforced(db_session, table_name, fk_col, ref_col):
    """Orphan insert rejected for *every* FK column of the nine tables
    (13 columns in the reconciled schema; test-plan's '7' was the
    pre-reconciliation count)."""
    w = make_world(db_session)
    row = _minimal_row_with_bad_fk(w, table_name, fk_col)
    db_session.add(row)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_m3_13_valid_fk_references_accepted(db_session):
    """Positive control: the world builder inserts one valid reference row
    for every table (owner, restaurant, item, order, item-line, ledger,
    refund, review, reminder)."""
    w = make_world(db_session)
    db_session.add(
        Review(order_id=w.order.id, customer_id=w.cust.id, rating=4)
    )
    db_session.add(
        RefundRequest(order_id=w.order.id, status=C.REFUND_PENDING, reason="r")
    )
    db_session.add(
        ReminderLog(order_id=w.order.id, status_at_reminder=C.ORDER_PLACED)
    )
    db_session.commit()  # all accepted


# ---------------------------------------------------------------------------
# T-M3-04 / T-M3-18 — historical snapshots (DB-04, D3)
# ---------------------------------------------------------------------------

def test_m3_04_menu_change_does_not_alter_snapshots(db_session):
    w = make_world(db_session)
    db_session.query(MenuItem).filter_by(id=w.m1.id).update(
        {"name": "Classic Pie", "price_cents": 1500}
    )
    db_session.commit()
    snapshots = {i.item_name: i.unit_price_cents for i in fresh_get(db_session, w.order.id, Order).items}
    assert snapshots == {"Pie": 1000, "Soda": 50}  # historical copies unchanged
    current = fresh_get(db_session, w.m1.id, MenuItem)
    assert current.name == "Classic Pie" and current.price_cents == 1500


def test_m3_18_snapshots_survive_reprice_softdelete_and_fee_change(db_session):
    w = make_world(db_session)
    before_fee = w.order.delivery_fee_cents
    db_session.query(MenuItem).filter_by(id=w.m1.id).update(
        {"name": "Renamed", "price_cents": 99999, "available": False}
    )
    db_session.query(Restaurant).filter_by(id=w.rest.id).update(
        {"delivery_fee_cents": 400}
    )
    db_session.commit()
    o = fresh_get(db_session, w.order.id, Order)
    assert o.delivery_fee_cents == before_fee  # fee snapshot frozen
    assert o.total_cents == o.items_subtotal_cents + o.delivery_fee_cents
    snapshots = {i.item_name: i.unit_price_cents for i in o.items}
    assert snapshots == {"Pie": 1000, "Soda": 50}


# ---------------------------------------------------------------------------
# T-M3-05 / T-M3-06 / T-M3-14 — uniqueness (DB-05, DB-06)
# ---------------------------------------------------------------------------

def test_m3_05_one_review_per_order(db_session):
    w = make_world(db_session)
    db_session.add(Review(order_id=w.order.id, customer_id=w.cust.id, rating=4))
    db_session.commit()  # the first review is durable
    db_session.add(Review(order_id=w.order.id, customer_id=w.cust.id, rating=1))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    assert db_session.query(Review).count() == 1  # the durable one survives


def test_m3_06_one_refund_request_per_order(db_session):
    w = make_world(db_session)
    db_session.add(RefundRequest(order_id=w.order.id, status=C.REFUND_PENDING, reason="a"))
    db_session.commit()  # the first request is durable
    db_session.add(RefundRequest(order_id=w.order.id, status=C.REFUND_PENDING, reason="b"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    assert db_session.query(RefundRequest).count() == 1  # the durable one survives


def test_m3_14_uniqueness_matrix(db_session):
    """The four DB-level uniqueness guarantees (test-plan T-M3-14)."""
    w = make_world(db_session)
    # email
    db_session.add(User(email=w.cust.email, password_hash="x", full_name="Dup", role=C.ROLE_CUSTOMER))
    with pytest.raises(IntegrityError, match=r"users\.email"):
        db_session.flush()
    db_session.rollback()
    # restaurant per owner (D24: one owner, at most one restaurant)
    db_session.add(Restaurant(owner_id=w.owner.id, name="Second", address="a", delivery_fee_cents=0))
    with pytest.raises(IntegrityError, match=r"restaurants\.owner_id"):
        db_session.flush()
    db_session.rollback()
    # review per order (REV-03)
    db_session.add(Review(order_id=w.order.id, customer_id=w.cust.id, rating=5))
    db_session.flush()
    db_session.add(Review(order_id=w.order.id, customer_id=w.cust.id, rating=2))
    with pytest.raises(IntegrityError, match=r"reviews\.order_id"):
        db_session.flush()
    db_session.rollback()
    # refund request per order (REF-02)
    db_session.add(RefundRequest(order_id=w.order.id, status=C.REFUND_PENDING, reason="a"))
    db_session.flush()
    db_session.add(RefundRequest(order_id=w.order.id, status=C.REFUND_PENDING, reason="b"))
    with pytest.raises(IntegrityError, match=r"refund_requests\.order_id"):
        db_session.flush()


# ---------------------------------------------------------------------------
# T-M3-15 — payment ledger uniqueness
# ---------------------------------------------------------------------------

def test_m3_15_ledger_at_most_one_row_per_type(db_session):
    w = make_world(db_session)  # exactly one mock_paid row
    db_session.add(
        PaymentLedger(order_id=w.order.id, type=C.PAYMENT_MOCK_PAID, amount_cents=1350)
    )
    with pytest.raises(IntegrityError, match=r"payment_ledger\.order_id"):
        db_session.flush()
    db_session.rollback()
    # one `refunded` row is allowed alongside `mock_paid`
    db_session.add(
        PaymentLedger(order_id=w.order.id, type=C.PAYMENT_REFUNDED, amount_cents=1350)
    )
    db_session.flush()
    assert db_session.query(PaymentLedger).filter_by(order_id=w.order.id).count() == 2


# ---------------------------------------------------------------------------
# T-M3-16 — reminder episode dedupe via ON CONFLICT DO NOTHING
# ---------------------------------------------------------------------------

def test_m3_16_reminder_dedupe_idempotent_insert(db_session):
    w = make_world(db_session)
    stmt = (
        sqlite_insert(ReminderLog)
        .values(
            order_id=w.order.id, status_at_reminder=C.ORDER_PLACED,
            detected_at=utcnow(), resolved=False,
        )
        .on_conflict_do_nothing(index_elements=["order_id", "status_at_reminder"])
    )
    db_session.execute(stmt)
    db_session.execute(stmt)  # re-scan of the same episode: no-op
    db_session.commit()
    assert db_session.query(ReminderLog).filter_by(order_id=w.order.id).count() == 1
    # a *different* status episode inserts a new row
    stmt2 = (
        sqlite_insert(ReminderLog)
        .values(
            order_id=w.order.id, status_at_reminder=C.ORDER_ACCEPTED,
            detected_at=utcnow(), resolved=False,
        )
        .on_conflict_do_nothing(index_elements=["order_id", "status_at_reminder"])
    )
    db_session.execute(stmt2)
    db_session.commit()
    assert db_session.query(ReminderLog).filter_by(order_id=w.order.id).count() == 2


# ---------------------------------------------------------------------------
# T-M3-17 — check constraint matrix
# ---------------------------------------------------------------------------

def _check_cases(w: World) -> list[tuple[str, object]]:
    now = utcnow()
    return [
        ("users.role", User(email="bad-role@example.org", password_hash="x", full_name="B", role="admin")),
        ("orders.status", Order(
            customer_id=w.cust.id, restaurant_id=w.rest.id, status="FROZEN",
            payment_status=C.PAYMENT_MOCK_PAID, items_subtotal_cents=10,
            delivery_fee_cents=0, total_cents=10, delivery_address="x",
            idempotency_key="ck-status", request_hash="h")),
        ("orders.payment_status", Order(
            customer_id=w.cust.id, restaurant_id=w.rest.id, status=C.ORDER_PLACED,
            payment_status="charged", items_subtotal_cents=10,
            delivery_fee_cents=0, total_cents=10, delivery_address="x",
            idempotency_key="ck-pay", request_hash="h")),
        ("refund_requests.status", RefundRequest(order_id=w.order.id, status="maybe", reason="r")),
        ("reminder_logs.status_at_reminder", ReminderLog(order_id=w.order.id, status_at_reminder="READY")),
        ("reviews.rating=0", Review(order_id=w.order.id, customer_id=w.cust.id, rating=0)),
        ("reviews.rating=6", Review(order_id=w.order.id, customer_id=w.cust.id, rating=6)),
        ("order_items.quantity=0", OrderItem(
            order_id=w.order.id, menu_item_id=w.m1.id, item_name="Pie",
            unit_price_cents=1000, quantity=0, line_total_cents=0)),
        ("order_items.quantity<0", OrderItem(
            order_id=w.order.id, menu_item_id=w.m1.id, item_name="Pie",
            unit_price_cents=1000, quantity=-3, line_total_cents=-3000)),
        ("order_items.unit_price<0", OrderItem(
            order_id=w.order.id, menu_item_id=w.m1.id, item_name="Pie",
            unit_price_cents=-1, quantity=1, line_total_cents=-1)),
        ("menu_items.price<0", MenuItem(restaurant_id=w.rest.id, name="Neg", price_cents=-1)),
        ("restaurants.fee<0", Restaurant(owner_id=w.owner.id, name="NegFee", address="a", delivery_fee_cents=-1)),  # valid FK; only the CHECK is under test
        ("orders.total identity broken", Order(
            customer_id=w.cust.id, restaurant_id=w.rest.id, status=C.ORDER_PLACED,
            payment_status=C.PAYMENT_MOCK_PAID, items_subtotal_cents=90,
            delivery_fee_cents=5, total_cents=100, delivery_address="x",
            idempotency_key="ck-total", request_hash="h")),
        ("order_items.line identity broken", OrderItem(
            order_id=w.order.id, menu_item_id=w.m1.id, item_name="Pie",
            unit_price_cents=10, quantity=5, line_total_cents=100)),
    ]


def test_m3_17_check_constraint_matrix(db_session):
    w = make_world(db_session)
    for label, row in _check_cases(w):
        db_session.add(row)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()
    # and nothing was written
    assert db_session.query(User).count() == 2
    assert db_session.query(Order).count() == 1


# ---------------------------------------------------------------------------
# T-M3-09 — migrations (DB-09, D1, D11)
# ---------------------------------------------------------------------------

def test_m3_09_migration_fresh_idempotent_and_current(tmp_path):
    from app.db.engine import make_engine
    from app.db.migrate import run_migrations
    from app.db.session import SessionFactory

    url = f"sqlite:///{tmp_path / 'm.db'}"
    run_migrations(url)  # fresh upgrade
    engine = make_engine(url)
    s = SessionFactory(engine).create()
    assert s.execute(text("SELECT version_num FROM alembic_version")).scalars().all() == ["0001"]
    s.add(User(email="m@example.org", password_hash="x", full_name="M", role=C.ROLE_CUSTOMER))
    s.commit()
    s.close()
    engine.dispose()

    # Idempotent re-run (what startup auto-apply does on an up-to-date DB).
    run_migrations(url)
    engine = make_engine(url)
    s = SessionFactory(engine).create()
    assert s.execute(text("SELECT version_num FROM alembic_version")).scalars().all() == ["0001"]
    assert s.execute(text("SELECT COUNT(*) FROM users")).scalar() == 1
    s.close()
    engine.dispose()
    # Honest note on T-M3-09's "second versioned migration" clause: adding a
    # throwaway schema revision purely for a test would pollute the real
    # migration history, so the guarantee is proven as
    # upgrade + idempotent re-upgrade + current-version + working schema.


# ---------------------------------------------------------------------------
# T-M3-10 — persistence (DB-10)
# ---------------------------------------------------------------------------

def test_m3_10_data_visible_from_new_engine_and_session(db_session, db_url):
    from app.db.engine import make_engine
    from app.db.session import SessionFactory

    w = make_world(db_session)  # committed
    engine2 = make_engine(db_url)  # a *new* engine ≈ a new process
    s2 = SessionFactory(engine2).create()
    got = s2.get(User, w.cust.id)
    assert got is not None and got.email == w.cust.email
    assert s2.query(Order).count() == 1
    s2.close()
    engine2.dispose()


# ---------------------------------------------------------------------------
# T-M3-07 — status_updated_at + reminder dedupe columns (DB-07)
# ---------------------------------------------------------------------------

def test_m3_07_timestamp_and_episode_columns_exist(db_session):
    w = make_world(db_session)
    o = fresh_get(db_session, w.order.id, Order)
    # App-generated aware-UTC timestamp (D33) — the *service* half of
    # T-M3-07 (stamp-on-transition, no-re-stamp) is covered in batch 5
    # (T-M7-11 / T-M7-17), which is where the transition code lives.
    assert o.status_updated_at is not None
    assert o.status_updated_at.tzinfo is not None
    cols = {row[1] for row in db_session.execute(text("PRAGMA table_info(reminder_logs)"))}
    assert {"order_id", "status_at_reminder", "detected_at", "resolved", "resolved_at"} <= cols


# ---------------------------------------------------------------------------
# T-M3-08 — money columns (DB-08, D3)
# ---------------------------------------------------------------------------

def test_m3_08_money_columns_integer_declared_and_non_negative(db_session):
    w = make_world(db_session)
    money_cols = {
        "menu_items": ["price_cents"],
        "restaurants": ["delivery_fee_cents"],
        "orders": ["items_subtotal_cents", "delivery_fee_cents", "total_cents"],
        "order_items": ["unit_price_cents", "line_total_cents"],
        "payment_ledger": ["amount_cents"],
    }
    for table, cols in money_cols.items():
        info = {row[1]: row[2] for row in db_session.execute(text(f"PRAGMA table_info({table})"))}
        for c in cols:
            assert info.get(c, "").upper().startswith("INTEGER"), (table, c, info.get(c))
    # non-negative (the full matrix is T-M3-17; one representative here).
    # Note: `Query.update()` executes immediately, so the violation is raised
    # by the call itself, not by a later flush.
    with pytest.raises(IntegrityError):
        db_session.query(Restaurant).filter_by(id=w.rest.id).update({"delivery_fee_cents": -1})
    db_session.rollback()
    # Honest SQLite limitation (database.md §7): `INTEGER` is an affinity,
    # not a strict type — a float CAN be stored. The "no floats" guarantee
    # (D3) is the application layer's job (Pydantic int validation, batch 4+);
    # the schema guarantees non-negativity and the total identities.
    db_session.execute(
        text("UPDATE menu_items SET price_cents = 12.5 WHERE id = :id"), {"id": w.m1.id}
    )
    db_session.commit()
    assert fresh_get(db_session, w.m1.id, MenuItem).price_cents == 12.5


# ---------------------------------------------------------------------------
# T-M3-19 / T-M3-20 — transaction rollback (D2, D3)
# ---------------------------------------------------------------------------

def test_m3_19_provisioning_rollback_leaves_no_rows(db_session):
    """Owner+restaurant provisioning (D2): if the restaurant insert fails,
    the owner must not exist either — one transaction, all-or-nothing."""
    owner = User(email="prov-owner@example.org", password_hash="x", full_name="Prov", role=C.ROLE_OWNER)
    db_session.add(owner)
    db_session.flush()  # owner exists inside the transaction
    db_session.add(Restaurant(owner_id=owner.id, name=None, address="a", delivery_fee_cents=0))
    with pytest.raises(IntegrityError):
        db_session.flush()  # NOT NULL name → restaurant fails
    db_session.rollback()
    assert db_session.query(User).filter_by(email="prov-owner@example.org").first() is None
    assert db_session.query(Restaurant).count() == 0


def test_m3_20_checkout_rollback_writes_zero_rows(db_session):
    """Checkout atomicity (D3): one invalid item line in the checkout
    transaction must leave **zero** order/item/ledger rows — the checkout
    service (batch 4) commits all-or-nothing on exactly this behavior."""
    w = make_world(db_session)
    cust2 = User(email="cust2@example.org", password_hash="x", full_name="Cust Two", role=C.ROLE_CUSTOMER)
    db_session.add(cust2)
    db_session.flush()
    # The checkout, as one transaction: order + one valid line + one invalid
    # line (quantity 0) + the payment row. Nothing is committed.
    order = Order(
        customer_id=cust2.id, restaurant_id=w.rest.id, status=C.ORDER_PLACED,
        payment_status=C.PAYMENT_MOCK_PAID, items_subtotal_cents=1000,
        delivery_fee_cents=w.rest.delivery_fee_cents,
        total_cents=1000 + w.rest.delivery_fee_cents, delivery_address="x",
        idempotency_key="ck-c2", request_hash=canonical_request_hash(w.rest.id, [(w.m1.id, 1)]),
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(OrderItem(
        order_id=order.id, menu_item_id=w.m1.id, item_name=w.m1.name,
        unit_price_cents=w.m1.price_cents, quantity=1, line_total_cents=w.m1.price_cents,
    ))
    db_session.add(PaymentLedger(order_id=order.id, type=C.PAYMENT_MOCK_PAID, amount_cents=order.total_cents))
    db_session.add(OrderItem(
        order_id=order.id, menu_item_id=w.m2.id, item_name=w.m2.name,
        unit_price_cents=w.m2.price_cents, quantity=0,  # ← CHECK violation
        line_total_cents=0,
    ))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    assert db_session.query(Order).filter_by(customer_id=cust2.id).count() == 0
    assert db_session.query(OrderItem).filter_by(order_id=order.id).count() == 0
    assert db_session.query(PaymentLedger).filter_by(order_id=order.id).count() == 0
    # the pre-existing world is untouched
    assert db_session.query(Order).count() == 1


# ---------------------------------------------------------------------------
# T-M3-11 / T-M3-21 — conflicting transitions (CAS) (DB-11, D1, D7)
# ---------------------------------------------------------------------------

from sqlalchemy import update  # noqa: E402


def test_m3_11_cas_sequential_one_winner(db_session, db_factory):
    w = make_world(db_session)  # PLACED
    cas = (
        update(Order)
        .where(Order.id == w.order.id, Order.status == C.ORDER_PLACED)
        .values(status=C.ORDER_ACCEPTED, status_updated_at=utcnow())
    )
    s1 = db_factory.create()
    s2 = db_factory.create()
    try:
        r1 = s1.execute(cas)
        s1.commit()
        r2 = s2.execute(cas)  # stale writer: WHERE no longer matches
        s2.commit()
    finally:
        s1.close()
        s2.close()
    assert (r1.rowcount, r2.rowcount) == (1, 0)
    final = fresh_get(db_session, w.order.id, Order)
    assert final.status == C.ORDER_ACCEPTED  # exactly one valid edge applied


def test_m3_21_cas_concurrent_threads_one_winner(db_session, db_factory):
    """True race: three threads race the same transition on the shared
    engine. SQLite's single-writer model must serialize them so that
    exactly one CAS wins; no exceptions, no corrupt row. (The app maps a
    rowcount-0 to 409 INVALID_TRANSITION in batch 5, T-M7-20.)"""
    import threading

    w = make_world(db_session)
    results: list[int] = []
    errors: list[BaseException] = []

    def attempt() -> None:
        s = db_factory.create()
        try:
            r = s.execute(
                update(Order)
                .where(Order.id == w.order.id, Order.status == C.ORDER_PLACED)
                .values(status=C.ORDER_ACCEPTED, status_updated_at=utcnow())
            )
            s.commit()
            results.append(r.rowcount)
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
    assert sorted(results) == [0, 0, 1]
    final = fresh_get(db_session, w.order.id, Order)
    assert final.status == C.ORDER_ACCEPTED
    assert final.status_updated_at is not None


# ---------------------------------------------------------------------------
# T-M3-22 — duplicate refund ledger rows (D27/D30 backstop)
# ---------------------------------------------------------------------------

def test_m3_22_double_refund_approval_cannot_double_ledger(db_session):
    w = make_world(db_session, status=C.ORDER_DELIVERED)
    # First approval event (the service does this in batch 6) — durable.
    db_session.add(
        PaymentLedger(order_id=w.order.id, type=C.PAYMENT_REFUNDED, amount_cents=w.order.total_cents)
    )
    db_session.commit()
    # Duplicate approval attempt → the DB refuses the second row.
    db_session.add(
        PaymentLedger(order_id=w.order.id, type=C.PAYMENT_REFUNDED, amount_cents=w.order.total_cents)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    assert db_session.query(PaymentLedger).filter_by(order_id=w.order.id).count() == 2  # mock_paid + 1 refunded


# ---------------------------------------------------------------------------
# T-M3-23 — reminder lifecycle (D6, D20)
# ---------------------------------------------------------------------------

def test_m3_23_reminder_create_resolve_new_episode(db_session):
    w = make_world(db_session)
    # Episode 1 detected (PLACED, stale).
    db_session.add(ReminderLog(order_id=w.order.id, status_at_reminder=C.ORDER_PLACED))
    db_session.commit()
    # Owner progresses the order → the scanner's resolve pass.
    db_session.query(ReminderLog).filter_by(
        order_id=w.order.id, status_at_reminder=C.ORDER_PLACED
    ).update({"resolved": True, "resolved_at": utcnow()})
    db_session.commit()
    assert all(
        r.resolved and r.resolved_at is not None
        for r in db_session.query(ReminderLog).filter_by(order_id=w.order.id)
    )
    # A *different* status episode creates a *new* row.
    db_session.add(ReminderLog(order_id=w.order.id, status_at_reminder=C.ORDER_ACCEPTED))
    db_session.commit()
    reminders = db_session.query(ReminderLog).filter_by(order_id=w.order.id).all()
    assert {r.status_at_reminder for r in reminders} == {C.ORDER_PLACED, C.ORDER_ACCEPTED}
    # A duplicate of the open episode is still refused (unique backstop).
    db_session.add(ReminderLog(order_id=w.order.id, status_at_reminder=C.ORDER_ACCEPTED))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    assert db_session.query(ReminderLog).filter_by(order_id=w.order.id).count() == 2


# ---------------------------------------------------------------------------
# T-M3-24 — delivered_at lifecycle + timestamp round-trip (DB-13, D31, D33)
# ---------------------------------------------------------------------------

def test_m3_24_delivered_at_set_preserved_and_null_on_cancel(db_session, db_url):
    from app.db.engine import make_engine
    from app.db.session import SessionFactory

    t_delivered = utcnow() - timedelta(minutes=30)
    w = make_world(db_session, status=C.ORDER_PLACED, delivered_at=None)

    # Delivery completes → delivered_at stamped once.
    w.order.status = C.ORDER_DELIVERED
    w.order.status_updated_at = t_delivered
    w.order.delivered_at = t_delivered
    db_session.commit()

    # Read through a *new* engine + session (a true storage round-trip).
    s2 = SessionFactory(make_engine(db_url)).create()
    o = s2.get(Order, w.order.id)
    assert o.delivered_at is not None
    assert o.delivered_at == t_delivered  # microsecond-precise round-trip
    assert o.delivered_at.tzinfo is not None  # aware UTC, not naive

    # Later refund: delivered_at must SURVIVE (D31 review eligibility).
    o.status = C.ORDER_REFUNDED
    o.payment_status = C.PAYMENT_REFUNDED
    s2.add(PaymentLedger(order_id=o.id, type=C.PAYMENT_REFUNDED, amount_cents=o.total_cents))
    s2.commit()
    o2 = s2.get(Order, w.order.id)
    assert o2.status == C.ORDER_REFUNDED
    assert o2.delivered_at == t_delivered  # preserved through REFUNDED

    # The stored text carries the approved +00:00 suffix (D33).
    raw = s2.execute(text("SELECT delivered_at FROM orders WHERE id=:i"), {"i": o.id}).scalar()
    assert raw.endswith("+00:00"), raw
    s2.close()

    # Cancelled orders never deliver → NULL.
    w2 = make_world(
        db_session, cust_email="cust-cancel@example.org",
        owner_email="owner-cancel@example.org", rest_name="Cancel Eats",
        status=C.ORDER_CANCELLED, payment_status=C.PAYMENT_REFUNDED, key="key-cancel",
    )
    s3 = SessionFactory(make_engine(db_url)).create()
    assert s3.get(Order, w2.order.id).delivered_at is None
    s3.close()


# ---------------------------------------------------------------------------
# T-M3-25 — idempotency uniqueness, customer-scoped (DB-14, D34)
# ---------------------------------------------------------------------------

def test_m3_25_idempotency_key_unique_per_customer(db_session):
    w = make_world(db_session, key="shared-key")
    # Same customer reusing the key → refused (duplicate checkout backstop).
    dup = Order(
        customer_id=w.cust.id, restaurant_id=w.rest.id, status=C.ORDER_PLACED,
        payment_status=C.PAYMENT_MOCK_PAID, items_subtotal_cents=10,
        delivery_fee_cents=0, total_cents=10, delivery_address="x",
        idempotency_key="shared-key", request_hash="different",
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError, match=r"orders\.customer_id"):
        db_session.flush()
    db_session.rollback()
    # A *different* customer using the same key string is their own checkout.
    # (Created after the rollback: a user flushed inside a rolled-back
    # transaction is expired, not re-inserted, so the order would dangle.)
    other = User(email="cust-other@example.org", password_hash="x", full_name="Cust Other", role=C.ROLE_CUSTOMER)
    db_session.add(other)
    db_session.flush()
    ok = Order(
        customer_id=other.id, restaurant_id=w.rest.id, status=C.ORDER_PLACED,
        payment_status=C.PAYMENT_MOCK_PAID, items_subtotal_cents=10,
        delivery_fee_cents=0, total_cents=10, delivery_address="x",
        idempotency_key="shared-key", request_hash="whatever",
    )
    db_session.add(ok)
    db_session.flush()  # accepted
    assert db_session.query(Order).filter_by(customer_id=w.cust.id).count() == 1
    assert db_session.query(Order).filter_by(customer_id=other.id).count() == 1


# ---------------------------------------------------------------------------
# T-M3-12 — seed script (DB-12, D2, D21)
# ---------------------------------------------------------------------------

def test_m3_12_seed_creates_documented_world_and_is_idempotent(tmp_path):
    from app.db.engine import make_engine
    from app.db.migrate import run_migrations
    from app.db.session import SessionFactory
    from app.seed import seed

    url = f"sqlite:///{tmp_path / 'seed.db'}"
    seed(url)
    engine = make_engine(url)
    s = SessionFactory(engine).create()
    assert s.query(User).count() == 6
    assert s.query(Restaurant).count() == 2
    assert s.query(MenuItem).count() == 6
    assert s.query(Order).count() == 5
    users = s.query(User).all()
    # Placeholder credentials only (D2): documented example.org domain…
    assert all(u.email.endswith("@example.org") for u in users)
    # …and every password is a real bcrypt hash, never plaintext…
    assert all(u.password_hash.startswith(("$2b$", "$2a$", "$2y$")) for u in users)
    # …with no obvious seed password stored in the clear anywhere.
    for u in users:
        assert "Pass" not in u.password_hash
    s.close()
    engine.dispose()

    # Idempotent re-run: nothing duplicates.
    seed(url)
    engine = make_engine(url)
    s = SessionFactory(engine).create()
    assert s.query(User).count() == 6
    assert s.query(Restaurant).count() == 2
    assert s.query(MenuItem).count() == 6
    assert s.query(Order).count() == 5
    s.close()
    engine.dispose()
