"""M10 AI insights tests (docs/test-plan.md §M10; D9, AI-01…AI-09).

The OpenAI provider is ALWAYS faked through the ``openai_client_factory``
seam on ``create_app`` — no network, no paid calls, ever (batch 10 rule).
The fake records the exact ``create()`` kwargs so the tests can assert on
the prompt itself: cross-customer isolation (AI-02) and PII exclusion
(AI-06) are properties of that prompt.
"""
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import APITimeoutError, OpenAIError, RateLimitError

from app.core import constants as C
from app.main import create_app
from tests.conftest import make_test_settings
from tests.test_auth import login_token
from tests.test_lifecycle import (
    KNOWN_PASSWORD,
    bearer,
    make_item,
    make_order,
    make_restaurant,
    make_user,
)

FAKE_ANSWER = "FAKE-ANSWER: you spent some money."
URL = "/api/v1/insights/question"


class FakeCompletions:
    """Records create() kwargs; returns canned content or raises."""

    def __init__(self, content: str = FAKE_ANSWER, raise_exc: Exception | None = None):
        self.content = content
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    def create(self, **kwargs) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.raise_exc is not None:
            raise self.raise_exc
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


def _fake_client(completions: FakeCompletions) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def _httpx_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.test/v1")


@pytest.fixture()
def completions() -> FakeCompletions:
    return FakeCompletions()


@pytest.fixture()
def settings(db_url) -> "object":
    # Keyed settings: the default path in this module exercises a
    # configured provider (with a fake). The no-key test builds its own.
    return make_test_settings(db_url, openai_api_key="sk-fake-not-real")


@pytest.fixture()
def app(settings, completions) -> "object":
    return create_app(settings, openai_client_factory=lambda: _fake_client(completions))


@pytest.fixture()
def client(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def world(client, db_session, db_url):
    cust1 = make_user(db_session, "ins-c1@example.org", C.ROLE_CUSTOMER, "Cust One")
    cust2 = make_user(db_session, "ins-c2@example.org", C.ROLE_CUSTOMER, "Cust Two")
    owner1 = make_user(db_session, "ins-o1@example.org", C.ROLE_OWNER, "Owner One")
    partner1 = make_user(db_session, "ins-p1@example.org", C.ROLE_PARTNER, "Partner One")
    rest1 = make_restaurant(db_session, owner1, "Alpha Pizza", fee=200)
    marg = make_item(db_session, rest1, "Margherita", 1299)
    garb = make_item(db_session, rest1, "Garlic Bread", 399)
    soda = make_item(db_session, rest1, "Soda", 150)
    gold = make_item(db_session, rest1, "Gold Pizza", 9999)
    db_session.commit()
    # cust1: one of each terminal-ish state. Money (fee 200):
    #   DELIVERED  1299+200 = 1499  mock_paid
    #   REFUNDED    399+200 =  599  refunded
    #   CANCELLED   150+200 =  350  refunded (D29 reversal)
    o_delivered = make_order(db_session, cust1, rest1, marg, status=C.ORDER_DELIVERED, fee=200)
    o_refunded = make_order(db_session, cust1, rest1, garb, status=C.ORDER_REFUNDED, fee=200)
    o_cancelled = make_order(db_session, cust1, rest1, soda, status=C.ORDER_CANCELLED, fee=200)
    # cust2: a distinct dish and amount for isolation assertions.
    o_other = make_order(db_session, cust2, rest1, gold, status=C.ORDER_PLACED, fee=200)
    return SimpleNamespace(
        cust1=cust1,
        cust2=cust2,
        owner1=owner1,
        partner1=partner1,
        rest1=rest1,
        o_delivered=o_delivered,
        o_refunded=o_refunded,
        o_cancelled=o_cancelled,
        o_other=o_other,
        tok_cust1=login_token(client, "ins-c1@example.org"),
        tok_cust2=login_token(client, "ins-c2@example.org"),
        tok_owner1=login_token(client, "ins-o1@example.org"),
        tok_partner1=login_token(client, "ins-p1@example.org"),
    )


def ask(client, token, question) -> "httpx.Response":
    return client.post(URL, headers=bearer(token), json={"question": question})


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

def test_m10_01_role_restriction(client, world):
    for token in (world.tok_owner1, world.tok_partner1):
        r = ask(client, token, "How much did I spend?")
        assert r.status_code == 403, r.text
        assert r.json()["code"] == "ROLE_FORBIDDEN"
    r = client.post(URL, json={"question": "How much did I spend?"})
    assert r.status_code == 401  # TOKEN_MISSING


# ---------------------------------------------------------------------------
# Happy path + exact app-computed stats (AI-05)
# ---------------------------------------------------------------------------

def test_m10_02_happy_path_and_stats(client, world, completions):
    r = ask(client, world.tok_cust1, "What did I spend in total?")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == FAKE_ANSWER
    assert body["provider"] == "openai:gpt-4o-mini"
    s = body["stats"]
    # gross = 1499 + 599 + 350 = 2448 (every placed order was mock-paid)
    assert s["gross_cents"] == 2448
    assert s["refunded_cents"] == 599 + 350
    assert s["net_retained_cents"] == 1499
    assert s["order_count"] == 3
    assert s["avg_order_cents"] == 2448 // 3
    # D31: a later-refunded order was still actually delivered, so it
    # counts (delivered_at is the source of truth, not current status).
    assert s["delivered_count"] == 2
    assert s["top_restaurants"] == ["Alpha Pizza"]
    assert set(s["top_dishes"]) == {"Margherita", "Garlic Bread", "Soda"}


def test_m10_03_prompt_contents_and_pii_exclusion(client, world, completions):
    ask(client, world.tok_cust1, "Summarize my spending.")
    assert len(completions.calls) == 1
    kwargs = completions.calls[0]
    prompt = kwargs["messages"][1]["content"]
    # The customer's own data is present…
    assert "Alpha Pizza" in prompt and "Margherita" in prompt
    assert "1299" in prompt  # integer cents, exact (AI-05)
    # …but personal details never leave the app (AI-06).
    assert "1 Student Ln" not in prompt  # delivery address
    assert "ins-c1@example.org" not in prompt  # e-mail
    system = kwargs["messages"][0]["content"]
    assert "only use" in system.lower() or "own" in system.lower()


# ---------------------------------------------------------------------------
# Cross-customer isolation (AI-02) — the assignment's key AI risk
# ---------------------------------------------------------------------------

def test_m10_04_cross_customer_isolation(client, world, completions):
    r = ask(client, world.tok_cust1, "Which dishes do I order?")
    assert r.status_code == 200
    prompt = completions.calls[0]["messages"][1]["content"]
    # cust2's order must be invisible in the prompt…
    assert "Gold Pizza" not in prompt
    assert "9999" not in prompt
    assert "10199" not in prompt
    # …and in the returned stats (aggregates cover cust1 only).
    assert r.json()["stats"]["gross_cents"] == 2448
    assert r.json()["stats"]["order_count"] == 3


def test_m10_05_no_target_customer_parameter(client, world, completions):
    # The endpoint accepts exactly {question}; extras are 422 (extra=forbid)
    # — a client cannot name another customer at all (AI-02).
    r = client.post(
        URL,
        headers=bearer(world.tok_cust1),
        json={"question": "hi", "customer_id": world.cust2.id},
    )
    assert r.status_code == 422
    assert len(completions.calls) == 0


# ---------------------------------------------------------------------------
# Graceful degradation without a key (D9)
# ---------------------------------------------------------------------------

def test_m10_06_unconfigured_returns_stats_not_fake_answer(db_url, db_session, world):
    settings = make_test_settings(db_url, openai_api_key=None)
    fake = FakeCompletions()
    app = create_app(settings, openai_client_factory=lambda: _fake_client(fake))
    with TestClient(app) as c:
        tok = login_token(c, "ins-c1@example.org")
        r = ask(c, tok, "What did I spend?")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "unconfigured"
    assert body["answer"] is None  # no fake AI output
    assert body["stats"]["gross_cents"] == 2448
    assert len(fake.calls) == 0  # no provider call was attempted


# ---------------------------------------------------------------------------
# Limits and bounds (AI-04)
# ---------------------------------------------------------------------------

def test_m10_07_question_too_long(client, world, completions):
    r = ask(client, world.tok_cust1, "x" * 501)
    assert r.status_code == 422
    assert r.json()["code"] == "QUESTION_TOO_LONG"
    assert len(completions.calls) == 0


def test_m10_08_empty_question(client, world, completions):
    r = ask(client, world.tok_cust1, "   ")
    assert r.status_code == 422
    assert r.json()["code"] == "QUESTION_EMPTY"


def test_m10_09_rate_limit(db_url, db_session, world):
    settings = make_test_settings(
        db_url, openai_api_key="sk-fake-not-real",
        ai_rate_limit=2, ai_rate_window_minutes=10,
    )
    fake = FakeCompletions()
    app = create_app(settings, openai_client_factory=lambda: _fake_client(fake))
    with TestClient(app) as c:
        tok = login_token(c, "ins-c1@example.org")
        assert ask(c, tok, "q1").status_code == 200
        assert ask(c, tok, "q2").status_code == 200
        r = ask(c, tok, "q3")
    assert r.status_code == 429
    assert r.json()["code"] == "RATE_LIMITED"
    assert len(fake.calls) == 2  # the 3rd never reached the provider


def test_m10_10_rate_limit_is_per_user(client, world, completions):
    # Default limit is 10/10min: cust1 hitting it must not block cust2.
    for i in range(10):
        assert ask(client, world.tok_cust1, f"q{i}").status_code == 200
    assert ask(client, world.tok_cust1, "q10").status_code == 429
    assert ask(client, world.tok_cust2, "q1").status_code == 200


# ---------------------------------------------------------------------------
# Empty history — deterministic, no provider call
# ---------------------------------------------------------------------------

def test_m10_11_no_orders_deterministic_answer(client, world, completions):
    # A brand-new customer (registered via the public API) has no orders:
    # the endpoint must answer deterministically and never call the model.
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "ins-fresh@example.org", "password": KNOWN_PASSWORD,
              "full_name": "Fresh Cust"},
    )
    assert r.status_code == 201, r.text
    r = ask(client, login_token(client, "ins-fresh@example.org"), "Summarize.")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "deterministic"
    assert body["stats"]["order_count"] == 0
    assert len(completions.calls) == 0


# ---------------------------------------------------------------------------
# Upstream failure mapping (AI-08) — controlled, no secrets/noise leaked
# ---------------------------------------------------------------------------

def _upstream_app(db_url, exc: Exception, key: str = "sk-fake-not-real"):
    settings = make_test_settings(db_url, openai_api_key=key)
    fake = FakeCompletions(raise_exc=exc)
    app = create_app(settings, openai_client_factory=lambda: _fake_client(fake))
    return app, fake


def test_m10_12_upstream_rate_limit_maps_429(db_url, world):
    req = _httpx_request()
    exc = RateLimitError("upstream busy", response=httpx.Response(429, request=req), body=None)
    app, fake = _upstream_app(db_url, exc)
    with TestClient(app) as c:
        tok = login_token(c, "ins-c1@example.org")
        r = ask(c, tok, "What did I spend?")
    assert r.status_code == 429
    assert r.json()["code"] == "AI_UPSTREAM_RATE_LIMITED"
    assert "upstream busy" not in r.text  # provider error text is not forwarded


def test_m10_13_timeout_maps_504(db_url, world):
    app, fake = _upstream_app(db_url, APITimeoutError(request=_httpx_request()))
    with TestClient(app) as c:
        tok = login_token(c, "ins-c1@example.org")
        r = ask(c, tok, "What did I spend?")
    assert r.status_code == 504
    assert r.json()["code"] == "AI_TIMEOUT"


def test_m10_14_generic_upstream_error_maps_502(db_url, world):
    app, fake = _upstream_app(db_url, OpenAIError("boom"))
    with TestClient(app) as c:
        tok = login_token(c, "ins-c1@example.org")
        r = ask(c, tok, "What did I spend?")
    assert r.status_code == 502
    assert r.json()["code"] == "AI_UPSTREAM_ERROR"
    assert "boom" not in r.text
