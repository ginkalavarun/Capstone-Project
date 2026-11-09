"""Dev-only seed data (D21).

Creates a small browsable world for local development: two customers, two
owners with their restaurants, two delivery partners, menus (some
unavailable dishes), and orders spread across the lifecycle — all with
**documented placeholder credentials** (example.org domains, obvious
passwords). This is explicitly a throwaway dev artifact:

- it targets the local dev database (never production),
- it is idempotent (re-running skips existing emails),
- it must never be the way a grader gets "real" accounts — use the
  provisioning CLI (batch 2) for that (D2).

Run from `backend/`:  `python -m app.seed`
Environment: DATABASE_URL (default: the local dev path).
"""
import os
import sys
from datetime import timedelta

from sqlalchemy import create_engine

from .core import constants as C
from .core.security import hash_password
from .core.utils import canonical_request_hash
from .db.engine import make_engine, utcnow
from .db.migrate import run_migrations
from .db.models import (
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
from .db.session import SessionFactory

DEV_DB_DEFAULT = "sqlite:///./data/campusbite-dev.db"

PLACEHOLDER_ACCOUNTS = [
    # (email, password, role, full_name, active)
    ("priya@example.org", "Customer-Pass-1", C.ROLE_CUSTOMER, "Priya Nair", True),
    ("dev@example.org", "Customer-Pass-2", C.ROLE_CUSTOMER, "Dev Menon", True),
    ("sam@example.org", "Owner-Pass-1", C.ROLE_OWNER, "Sam Kapoor", True),
    ("lena@example.org", "Owner-Pass-2", C.ROLE_OWNER, "Lena Fischer", True),
    ("dana@example.org", "Partner-Pass-1", C.ROLE_PARTNER, "Dana Kim", True),
    ("marco@example.org", "Partner-Pass-2", C.ROLE_PARTNER, "Marco Rossi", True),
]


def _seed_accounts(session) -> dict[str, User]:
    """Idempotent user creation; returns email -> user."""
    users: dict[str, User] = {}
    for email, password, role, name, active in PLACEHOLDER_ACCOUNTS:
        user = session.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                full_name=name,
                role=role,
                is_active=active,
            )
            session.add(user)
            session.flush()
        users[email] = user
    return users


def _make_order(
    session,
    customer: User,
    restaurant: Restaurant,
    lines: list[tuple[MenuItem, int]],
    *,
    status: str,
    payment_status: str,
    idempotency_key: str,
    address: str,
    age_minutes: int = 0,
    partner: User | None = None,
    delivered_minutes_ago: int | None = None,
) -> Order:
    """Build one order + items + ledger rows with server-side money (D3)."""
    now = utcnow()
    created = now - timedelta(minutes=age_minutes)
    subtotal = 0
    for item, _qty in lines:
        subtotal += item.price_cents
    fee = restaurant.delivery_fee_cents
    total = subtotal + fee
    request_hash = canonical_request_hash(
        restaurant.id, [(item.id, qty) for item, qty in lines]
    )
    order = Order(
        customer_id=customer.id,
        restaurant_id=restaurant.id,
        delivery_partner_id=partner.id if partner else None,
        status=status,
        payment_status=payment_status,
        status_updated_at=now - timedelta(minutes=min(age_minutes, 15)),
        delivered_at=now - timedelta(minutes=delivered_minutes_ago)
        if delivered_minutes_ago is not None
        else None,
        items_subtotal_cents=subtotal,
        delivery_fee_cents=fee,
        total_cents=total,
        delivery_address=address,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        created_at=created,
        updated_at=now,
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
        PaymentLedger(
            order_id=order.id,
            type=C.PAYMENT_MOCK_PAID,
            amount_cents=total,
            created_at=created,
        )
    )
    if payment_status == C.PAYMENT_REFUNDED:
        session.add(
            PaymentLedger(
                order_id=order.id,
                type=C.PAYMENT_REFUNDED,
                amount_cents=total,
                created_at=now,
            )
        )
    return order


def seed(database_url: str | None = None) -> None:
    database_url = database_url or os.environ.get("DATABASE_URL", DEV_DB_DEFAULT)
    engine = make_engine(database_url)
    run_migrations(database_url)
    session = SessionFactory(engine).create()

    try:
        users = _seed_accounts(session)
        existing_restaurants = session.query(Restaurant).all()
        if not existing_restaurants:
            slice_house = Restaurant(
                owner_id=users["sam@example.org"].id,
                name="Slice House",
                description="Wood-fired pizzas on campus.",
                address="10 Green Line, Block A",
                delivery_fee_cents=200,
            )
            bagel_bros = Restaurant(
                owner_id=users["lena@example.org"].id,
                name="Bagel Bros",
                description="New York style bagels.",
                address="5 Green Line, Block C",
                delivery_fee_cents=300,
            )
            session.add_all([slice_house, bagel_bros])
            session.flush()

            menu = [
                MenuItem(restaurant_id=slice_house.id, name="Margherita Pizza", price_cents=1299, available=True),
                MenuItem(restaurant_id=slice_house.id, name="Garlic Bread", price_cents=399, available=True),
                MenuItem(restaurant_id=slice_house.id, name="Truffle Pasta", price_cents=1899, available=True),
                MenuItem(restaurant_id=slice_house.id, name="Old Special", price_cents=999, available=False),
                MenuItem(restaurant_id=bagel_bros.id, name="Everything Bagel", price_cents=450, available=True),
                MenuItem(restaurant_id=bagel_bros.id, name="Cream Cheese", price_cents=120, available=True),
            ]
            session.add_all(menu)
            session.flush()
            mi = {m.name: m for m in menu}
        else:
            # Re-run: look up menu items by name for the orders below.
            menu = session.query(MenuItem).all()
            mi = {m.name: m for m in menu}
            slice_house = next(
                r for r in existing_restaurants if r.name == "Slice House"
            )
            bagel_bros = next(
                r for r in existing_restaurants if r.name == "Bagel Bros"
            )

        # ---- Orders across the lifecycle (idempotent via the key) ----
        orders = session.query(Order).all()
        have_keys = {o.idempotency_key for o in orders}

        def maybe(
            key: str,
            builder,
        ) -> None:
            if key in have_keys:
                return
            builder()
            have_keys.add(key)

        priya = users["priya@example.org"]
        dev = users["dev@example.org"]
        dana = users["dana@example.org"]
        marco = users["marco@example.org"]
        addr_p = "42 Maple Hall, Room 12"
        addr_d = "8 Birch Court, Room 3"

        maybe("seed-1", lambda: _make_order(
            session, priya, slice_house,
            [(mi["Margherita Pizza"], 2), (mi["Garlic Bread"], 1)],
            status=C.ORDER_PLACED, payment_status=C.PAYMENT_MOCK_PAID,
            idempotency_key="seed-1", address=addr_p, age_minutes=5,
        ))
        maybe("seed-2", lambda: _make_order(
            session, priya, slice_house,
            [(mi["Truffle Pasta"], 1)],
            status=C.ORDER_DELIVERED, payment_status=C.PAYMENT_MOCK_PAID,
            idempotency_key="seed-2", address=addr_p,
            age_minutes=300, partner=marco, delivered_minutes_ago=240,
        ))
        # Stale on purpose: 20 min in ACCEPTED → the scanner will remind.
        maybe("seed-3", lambda: _make_order(
            session, dev, bagel_bros,
            [(mi["Everything Bagel"], 3)],
            status=C.ORDER_ACCEPTED, payment_status=C.PAYMENT_MOCK_PAID,
            idempotency_key="seed-3", address=addr_d, age_minutes=20,
        ))
        maybe("seed-4", lambda: _make_order(
            session, dev, slice_house,
            [(mi["Garlic Bread"], 2)],
            status=C.ORDER_CANCELLED, payment_status=C.PAYMENT_REFUNDED,
            idempotency_key="seed-4", address=addr_d, age_minutes=180,
        ))
        maybe("seed-5", lambda: _make_order(
            session, priya, bagel_bros,
            [(mi["Everything Bagel"], 1), (mi["Cream Cheese"], 1)],
            status=C.ORDER_ASSIGNED, payment_status=C.PAYMENT_MOCK_PAID,
            idempotency_key="seed-5", address=addr_p, age_minutes=120,
            partner=dana,
        ))
        session.flush()

        # Review for the delivered order (idempotent via the DB unique).
        delivered = session.query(Order).filter(
            Order.idempotency_key == "seed-2"
        ).first()
        if delivered and not session.query(Review).filter(
            Review.order_id == delivered.id
        ).first():
            session.add(
                Review(
                    order_id=delivered.id,
                    customer_id=priya.id,
                    rating=5,
                    comment="Truffle pasta was excellent.",
                )
            )
        # A pending refund request on the delivered order for the owner queue.
        if delivered and not session.query(RefundRequest).filter(
            RefundRequest.order_id == delivered.id
        ).first():
            session.add(
                RefundRequest(
                    order_id=delivered.id,
                    status=C.REFUND_PENDING,
                    reason="Arrived a bit cold",
                )
            )
        # An unresolved reminder for the stale ACCEPTED order.
        stale = session.query(Order).filter(
            Order.idempotency_key == "seed-3"
        ).first()
        if stale and not session.query(ReminderLog).filter(
            ReminderLog.order_id == stale.id
        ).first():
            session.add(
                ReminderLog(
                    order_id=stale.id,
                    status_at_reminder=C.ORDER_ACCEPTED,
                    detected_at=utcnow(),
                    resolved=False,
                )
            )

        session.commit()
        print(
            f"Seeded dev world into {database_url} "
            f"({session.query(User).count()} users, "
            f"{session.query(Order).count()} orders)."
        )
        print(
            "Placeholder logins (dev only, D21): "
            + ", ".join(email for email, *_ in PLACEHOLDER_ACCOUNTS)
        )
    finally:
        session.close()
        engine.dispose()


def main() -> None:
    seed()


if __name__ == "__main__":
    main()
