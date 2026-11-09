"""The central checkout service (batch 4; CK-01…10, D3/D25/D34).

This is the **single place an order comes into existence** (D7: transitions
live in `services/transitions.py`, batch 5; money rules live here).

Untrusted-input doctrine (CK-02, D3):
- the customer is the *authenticated* user — never a field in the body;
- item names, unit prices, the delivery fee, and every total come from the
  database, computed here;
- duplicate lines for the same menu item are merged (the request hash and the
  stored lines treat a dish as one line).

Idempotency (D34, §6 of docs/database.md):
- the key is scoped to the authenticated customer
  (`UNIQUE(customer_id, idempotency_key)` is the database backstop);
- identical retry  → the original order is returned (no new rows);
- same key, different payload → `409 IDEMPOTENCY_MISMATCH`;
- a losing concurrent insert (unique violation) re-reads the winner.
"""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core import constants as C
from ..core.errors import ApiError
from ..core.utils import canonical_request_hash
from ..db.engine import utcnow
from ..db.models import MenuItem, Order, OrderItem, PaymentLedger, Restaurant, User
from ..schemas.orders import CheckoutIn


def _merge_lines(items) -> list[tuple[int, int]]:
    """[(menu_item_id, quantity), …] with duplicate ids summed, sorted — the
    same canonical form `canonical_request_hash` uses (D34)."""
    quantities: dict[int, int] = {}
    for line in items:
        quantities[line.menu_item_id] = quantities.get(line.menu_item_id, 0) + line.quantity
    return sorted(quantities.items())


def place_order(db: Session, user: User, payload: CheckoutIn) -> tuple[Order, bool]:
    """Place the caller's order, or return the existing one on an idempotent
    retry. Returns ``(order, created)`` — the router uses ``created`` for the
    201/200 status code (docs/api-contract.md §orders)."""
    # Check 2 (D8): only customers place orders.
    if user.role != C.ROLE_CUSTOMER:
        raise ApiError(403, "ROLE_FORBIDDEN", "Only customers can place orders.")

    lines = _merge_lines(payload.items)
    item_ids = [mid for mid, _ in lines]
    items = {
        i.id: i
        for i in db.query(MenuItem).filter(MenuItem.id.in_(item_ids)).all()
    }

    # CK-04 validation — all failures are 422, nothing is written.
    missing = [mid for mid in item_ids if mid not in items]
    if missing:
        raise ApiError(422, "VALIDATION_ERROR", f"Menu item(s) not found: {missing}.")
    restaurant_ids = {i.restaurant_id for i in items.values()}
    if len(restaurant_ids) > 1:  # D25: one restaurant per order
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "A single order can contain dishes from one restaurant only.",
        )
    unavailable = sorted(i.name for i in items.values() if not i.available)
    if unavailable:  # MENU-07
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            f"Not available: {', '.join(unavailable)}.",
        )

    # Server-side money (D3): snapshots + integer-cent arithmetic, EUR (D26).
    restaurant_id = next(iter(restaurant_ids))
    restaurant = db.get(Restaurant, restaurant_id)
    assert restaurant is not None  # items exist ⇒ restaurant exists (FK)
    subtotal = sum(items[mid].price_cents * qty for mid, qty in lines)
    fee = restaurant.delivery_fee_cents
    total = subtotal + fee
    request_hash = canonical_request_hash(restaurant_id, lines)

    # Idempotency (D34): customer-scoped key.
    existing = (
        db.query(Order)
        .filter(Order.customer_id == user.id, Order.idempotency_key == payload.idempotency_key)
        .first()
    )
    if existing is not None:
        if existing.request_hash == request_hash:
            return existing, False  # identical retry → original order
        raise ApiError(
            409,
            "IDEMPOTENCY_MISMATCH",
            "This idempotency key was already used for a different order.",
        )

    now = utcnow()
    order = Order(
        customer_id=user.id,
        restaurant_id=restaurant_id,
        status=C.ORDER_PLACED,
        payment_status=C.PAYMENT_MOCK_PAID,
        status_updated_at=now,
        delivered_at=None,
        items_subtotal_cents=subtotal,
        delivery_fee_cents=fee,
        total_cents=total,
        delivery_address=payload.delivery_address,
        idempotency_key=payload.idempotency_key,
        request_hash=request_hash,
        created_at=now,
        updated_at=now,
    )
    db.add(order)
    try:
        # The flush INSERTs the order row (and assigns its id). In a race,
        # the UNIQUE(customer_id, idempotency_key) backstop fires *here*, so
        # the flush must be inside this try, not before it.
        db.flush()
        for mid, qty in lines:
            item = items[mid]
            db.add(
                OrderItem(
                    order_id=order.id,
                    menu_item_id=mid,
                    item_name=item.name,  # snapshot (D3)
                    unit_price_cents=item.price_cents,  # snapshot (D3)
                    quantity=qty,
                    line_total_cents=item.price_cents * qty,
                )
            )
        # CK-05/PAY-01: the mock payment event, in the same transaction.
        db.add(PaymentLedger(order_id=order.id, type=C.PAYMENT_MOCK_PAID, amount_cents=total))
        db.commit()
    except IntegrityError:
        # T-M6-13: a competing checkout with the same key committed first —
        # the UNIQUE(customer_id, idempotency_key) backstop fired. Re-read the
        # winner (after rollback, ORM objects are expired: query again).
        db.rollback()
        winner = (
            db.query(Order)
            .filter(Order.customer_id == user.id, Order.idempotency_key == payload.idempotency_key)
            .first()
        )
        if winner is not None and winner.request_hash == request_hash:
            return winner, False
        raise ApiError(
            409,
            "IDEMPOTENCY_MISMATCH",
            "This idempotency key was already used for a different order.",
        )
    db.refresh(order)
    return order, True
