"""Stale-order reminder scanner (batch 7: BG-01…05, D6, D20, D33).

**Why a scanner instead of request-triggered `BackgroundTasks` (D6):**
background tasks only run while requests arrive — the exact situation in
which a forgotten order does *not* need reminding. A managed periodic
scanner started through the application lifespan runs regardless of
traffic, every 60 s in the documented single-worker configuration (D1).

**What a scan does (`scan_once`, one short transaction):**
1. **Detect** — every order in `PLACED` or `ACCEPTED` whose
   `status_updated_at` is *older than* the stale threshold (15 min
   default) gets a reminder row for its current status episode, if it has
   none yet. A stale order whose episode row already exists (created by an
   earlier tick) gets nothing — "one reminder per status episode, not per
   tick" (D6). The database backstop is `uq_reminders_episode`
   `(order_id, status_at_reminder)`, D20.
2. **Resolve** — an open reminder whose order has left that status is
   marked `resolved` (D6: "hidden or marked resolved"). The approved
   machine has **no state recurrence** (an order is never PLACED or
   ACCEPTED twice — see the `ReminderLog` docstring), so "the order's
   current status differs" is a precise, non-ambiguous end-of-episode
   signal.

**Episode key justification (D20):** because no status can recur per
order, `(order_id, status_at_reminder)` fully identifies an episode and
no separate episode counter is needed — the model's unique constraint is
the dedupe mechanism.

**Clock injection (D6):** `ReminderScanner` takes a `clock` callable
(default `utcnow`). Tests advance a fake clock by minutes — no real
15-minute waits.

**Threading (D1/D6):** one scanner per documented single-worker app. Each
scan opens a *fresh* session (closed in `finally`) and does one short
write transaction. A failing scan is logged with its exception and the
loop continues (BG-05); `stop()` joins the thread for clean lifespan
shutdown.
"""
import logging
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional

from sqlalchemy.orm import Session

from ..core import constants as C
from ..db.engine import utcnow
from ..db.models import Order, ReminderLog
from ..db.session import SessionFactory

logger = logging.getLogger("campusbite.reminders")

#: The only states a reminder can refer to (ck_reminders_status).
STALE_STATES = (C.ORDER_PLACED, C.ORDER_ACCEPTED)


def scan_once(db: Session, now: datetime, stale_minutes: int) -> int:
    """Run one scan in the caller's session. Returns #reminders created.

    The caller (the scanner thread, or a test) owns the session and calls
    `commit`-free semantics: this function commits the short write
    transaction itself and is the only writer to `reminder_logs`.
    """
    cutoff = now - timedelta(minutes=stale_minutes)

    stale_orders = (
        db.query(Order)
        .filter(Order.status.in_(STALE_STATES), Order.status_updated_at < cutoff)
        .all()
    )
    created = 0
    for order in stale_orders:
        has_row = (
            db.query(ReminderLog)
            .filter_by(order_id=order.id, status_at_reminder=order.status)
            .count()
        )
        if has_row == 0:
            db.add(
                ReminderLog(
                    order_id=order.id,
                    status_at_reminder=order.status,
                    detected_at=now,
                    resolved=False,
                )
            )
            created += 1

    # Resolve reminders whose episode ended (the order left that status).
    for row in db.query(ReminderLog).filter(ReminderLog.resolved.is_(False)).all():
        order = db.get(Order, row.order_id)
        if order is None or order.status != row.status_at_reminder:
            row.resolved = True
            row.resolved_at = now

    db.commit()
    return created


class ReminderScanner:
    """The managed scanner thread (D6) — see module docstring.

    `clock` is injectable for tests; `interval_seconds` is the scan period
    (60 s in production per settings). The loop itself never touches the
    database — each tick delegates to `run_scan` on a fresh session.
    """

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        interval_seconds: float,
        stale_minutes: int,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._factory = session_factory
        self._interval = interval_seconds
        self._stale_minutes = stale_minutes
        self._clock = clock or utcnow
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._scans = 0
        self._errors = 0

    # -- observability ---------------------------------------------------
    @property
    def scans(self) -> int:
        return self._scans

    @property
    def errors(self) -> int:
        return self._errors

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- one tick --------------------------------------------------------
    def run_scan(self) -> int:
        """One scan on a **fresh session** (D1). Also the direct entry
        point tests use with a fake clock — no thread, no waiting. The
        session is always closed, even on error; the exception propagates
        so a *loop* caller can decide (log + continue)."""
        session = self._factory.create()
        try:
            return scan_once(session, self._clock(), self._stale_minutes)
        finally:
            session.close()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self._interval)
            if self._stop.is_set():
                break
            try:
                self.run_scan()
                self._scans += 1
            except Exception:  # noqa: BLE001 — BG-05: log, never crash
                self._errors += 1
                logger.exception("reminder scan failed; loop continues")

    # -- lifecycle (called from the application lifespan) -----------------
    def start(self) -> None:
        if self._thread is not None:
            return  # idempotent
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="reminder-scanner", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        """Signal shutdown and wait for the thread to exit (clean
        lifespan shutdown, BG-05)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
