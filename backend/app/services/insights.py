"""Customer order insights with OpenAI (D9; AI-01…AI-09, batch 10).

Security rules (D9 — read before changing):

- The OpenAI key exists only in backend environment configuration. It is
  never returned in a response, never logged, and never sent to the
  frontend.
- The model context contains **only the authenticated customer's own
  orders** — the customer ID is the token's subject; there is no
  client-supplied target-customer field (AI-02).
- No model-generated SQL and no arbitrary database tool access (AI-03):
  the model receives a pre-computed, length-bounded summary built by this
  module. Delivery addresses and e-mail addresses are excluded (AI-06:
  minimal personal information).
- Exact monetary aggregates are computed **in application code** (AI-05)
  and returned in `stats` verbatim; the model may *describe* them but is
  never trusted with the arithmetic.
- Question length (``ai_max_question_chars``) and history size
  (``ai_history_window``) are bounded by settings (AI-04).
- Upstream failures map to controlled responses (AI-08): provider rate
  limit → 429, timeout → 504, other API errors → 502. The provider's own
  error text is not forwarded (it can be noisy/PII-adjacent).
- **Rate-limit limitation (documented, D9):** the per-user limiter is
  in-memory. It resets on process restart and is only correct for the
  documented single-backend-worker deployment.
- Without an API key the endpoint still succeeds (200) with
  ``provider="unconfigured"``, ``answer=None`` and the exact app-computed
  ``stats`` — the feature degrades to a clear configuration message
  instead of failing, and no fake answer is ever presented as AI output.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from typing import Any, Callable, Optional

from openai import APITimeoutError, APIStatusError, OpenAI, OpenAIError, RateLimitError
from sqlalchemy.orm import Session

from ..core import constants as C
from ..core.config import Settings
from ..core.errors import ApiError
from ..db.models import Order

logger = logging.getLogger("campusbite.insights")

# The model is asked to keep answers short and plain.
_MAX_ANSWER_TOKENS = 300


class InMemoryRateLimiter:
    """Per-user sliding window limiter.

    In-memory by design (D9): state resets on restart and the limiter only
    works for the documented single-worker deployment. A lock protects the
    window because FastAPI may serve synchronous endpoints on a threadpool.
    ``now`` accepts a controlled clock in tests (monotonic seconds).
    """

    def __init__(self, limit: int, window_minutes: int) -> None:
        self.limit = max(1, int(limit))
        self.window_seconds = max(60, int(window_minutes) * 60)
        self._hits: dict[int, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, user_id: int, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[user_id]
            cutoff = now - self.window_seconds
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


@dataclass
class InsightResult:
    """`answer` is None when the provider is unconfigured or the customer
    has no orders (the latter gets a deterministic, non-AI sentence)."""

    answer: Optional[str]
    provider: str  # "openai:<model>" | "deterministic" | "unconfigured"
    stats: dict[str, Any]


def compute_stats(orders: list[Order]) -> dict[str, Any]:
    """Exact aggregates in application code (AI-05), integer cents.

    Metric definitions mirror the owner statistics (D35):
    - `gross_cents`: every placed order was mock-paid at checkout, so this
      is the sum of all order totals (including later cancelled/refunded).
    - `refunded_cents`: sum of totals of orders whose payment is refunded
      (approved refunds and PLACED-cancellation reversals).
    - `net_retained_cents`: gross − refunded.
    - `delivered_count`: orders with a `delivered_at` stamp — this
      **includes** later-refunded orders (D31 semantics).
    """
    gross = sum(o.total_cents for o in orders)
    refunded = sum(o.total_cents for o in orders if o.payment_status == C.PAYMENT_REFUNDED)
    delivered = [o for o in orders if o.delivered_at is not None]
    restaurants: Counter[str] = Counter()
    dishes: Counter[str] = Counter()
    for o in orders:
        restaurants[o.restaurant.name if o.restaurant is not None else "Unknown"] += 1
        for line in o.items:
            dishes[line.item_name] += line.quantity
    return {
        "order_count": len(orders),
        "gross_cents": gross,
        "refunded_cents": refunded,
        "net_retained_cents": gross - refunded,
        "avg_order_cents": (gross // len(orders)) if orders else 0,
        "delivered_count": len(delivered),
        "top_restaurants": [name for name, _ in restaurants.most_common(3)],
        "top_dishes": [name for name, _ in dishes.most_common(3)],
    }


def _context_block(orders: list[Order], currency: str) -> str:
    """The ONLY data the model sees: a bounded, PII-light summary of the
    customer's own orders. No addresses, no e-mails, no other customers."""
    rows = []
    for o in orders:  # already sorted newest-first, window-bounded
        rows.append(
            {
                "order_id": o.id,
                "restaurant": o.restaurant.name if o.restaurant is not None else "Unknown",
                "status": o.status,
                "payment_status": o.payment_status,
                "placed_on": o.created_at.date().isoformat(),
                f"total_{currency.lower()}_cents": o.total_cents,
                "items": [
                    {
                        "name": line.item_name,
                        "quantity": line.quantity,
                        f"unit_price_{currency.lower()}_cents": line.unit_price_cents,
                    }
                    for line in o.items
                ],
            }
        )
    return json.dumps(rows, ensure_ascii=False)


class InsightsService:
    def __init__(
        self,
        settings: Settings,
        limiter: InMemoryRateLimiter,
        openai_client_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.settings = settings
        self.limiter = limiter
        # Factory (not client) so tests can inject fakes per app instance;
        # the real client is built lazily, only when a key is present.
        self._openai_client_factory = openai_client_factory

    # -- helpers ---------------------------------------------------------

    def _client(self):
        if self._openai_client_factory is not None:
            return self._openai_client_factory()
        return OpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.openai_timeout_seconds,
        )

    # -- main entry point ------------------------------------------------

    def answer_question(self, db: Session, user, question: str) -> InsightResult:
        s = self.settings
        q = (question or "").strip()
        if not q:
            raise ApiError(422, "QUESTION_EMPTY", "Please enter a question.")
        if len(q) > s.ai_max_question_chars:
            raise ApiError(
                422,
                "QUESTION_TOO_LONG",
                f"Questions are limited to {s.ai_max_question_chars} characters.",
            )
        if not self.limiter.allow(user.id):
            raise ApiError(
                429,
                "RATE_LIMITED",
                f"You have reached the limit of {s.ai_rate_limit} insights "
                f"per {s.ai_rate_window_minutes} minutes. Please wait a bit.",
            )

        # Isolation (AI-02): the query is scoped to the token's user. The
        # endpoint has no target-customer parameter, by design.
        orders = (
            db.query(Order)
            .filter(Order.customer_id == user.id)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(s.ai_history_window)
            .all()
        )
        stats = compute_stats(orders)
        if not orders:
            return InsightResult(
                answer=(
                    "You have not placed any orders yet, so there is no "
                    "history to analyze. Once you order, I can help with "
                    "totals, favourites, and timing."
                ),
                provider="deterministic",
                stats=stats,
            )

        if not s.has_openai_key:
            # D9 graceful degradation: real stats, no fake AI answer.
            return InsightResult(answer=None, provider="unconfigured", stats=stats)

        system = (
            "You are a concise, friendly assistant for a campus food-delivery "
            "app. You may only use the JSON data about this customer's OWN "
            "orders that the application provides. Never invent numbers or "
            "data. Amounts are integer cents in "
            f"{s.currency}. If the data cannot answer the question, say so "
            "briefly. Keep the answer under ~120 words, plain text, no "
            "markdown tables."
        )
        user_prompt = (
            f"Question: {q}\n\n"
            f"Data (most recent first, {len(orders)} orders, {s.currency} "
            f"cents):\n{_context_block(orders, s.currency)}"
        )
        try:
            completion = self._client().chat.completions.create(
                model=s.openai_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=_MAX_ANSWER_TOKENS,
                timeout=s.openai_timeout_seconds,
            )
            answer = (completion.choices[0].message.content or "").strip()
            if not answer:
                raise ApiError(
                    502, "AI_UPSTREAM_ERROR", "The model returned an empty answer."
                )
        except APITimeoutError:
            logger.warning("insights: OpenAI timeout for user %s", user.id)
            raise ApiError(
                504, "AI_TIMEOUT", "The AI provider took too long to respond. Please try again."
            )
        except RateLimitError:
            logger.warning("insights: OpenAI upstream rate limit for user %s", user.id)
            raise ApiError(
                429,
                "AI_UPSTREAM_RATE_LIMITED",
                "The AI provider is busy right now. Please try again shortly.",
            )
        except APIStatusError as exc:
            logger.warning(
                "insights: OpenAI API error %s for user %s", exc.status_code, user.id
            )
            raise ApiError(502, "AI_UPSTREAM_ERROR", "The AI provider failed. Please try again.")
        except OpenAIError as exc:
            # Deliberately not logging the exception text: it can contain
            # request details. The code is safe and stable.
            logger.warning("insights: OpenAI error (%s) for user %s", type(exc).__name__, user.id)
            raise ApiError(502, "AI_UPSTREAM_ERROR", "The AI provider failed. Please try again.")

        return InsightResult(answer=answer, provider=f"openai:{s.openai_model}", stats=stats)


def build_insights_service(
    settings: Settings, openai_client_factory: Optional[Callable[[], Any]] = None
) -> InsightsService:
    return InsightsService(
        settings=settings,
        limiter=InMemoryRateLimiter(settings.ai_rate_limit, settings.ai_rate_window_minutes),
        openai_client_factory=openai_client_factory,
    )
