"""M8 request-logging middleware tests (docs/test-plan.md §M8: T-M8-08…10,
MW-01…03, D4/D23).

The middleware itself has existed since batch 1 (wired in `app/main.py`);
these tests pin its **security contract**: what it logs (method, path,
status, duration, request ID) and — critically — what it never logs
(Authorization headers, tokens, passwords, API keys, addresses).

Log capture uses pytest's `caplog` against the `campusbite.request`
logger; the TestClient runs the real middleware stack.
"""
import logging
import re
from types import SimpleNamespace

import pytest

from app.core import constants as C
from tests.test_auth import login_token
from tests.test_lifecycle import bearer, make_user

LOG_NAME = "campusbite.request"


@pytest.fixture()
def world(client, db_session):
    customer = make_user(db_session, "cust1@example.org", C.ROLE_CUSTOMER, "Cust 1")
    db_session.commit()
    return SimpleNamespace(
        customer=customer,
        tok_customer=login_token(client, "cust1@example.org"),
    )


def logged_messages(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == LOG_NAME
    ]


# ---------------------------------------------------------------------------
# T-M8-08 / MW-01 — method + path are logged
# ---------------------------------------------------------------------------

def test_m8_08_logs_method_and_path(client, world, caplog):
    with caplog.at_level(logging.INFO, logger=LOG_NAME):
        client.get("/api/v1/auth/me", headers=bearer(world.tok_customer))
    msgs = logged_messages(caplog)
    assert msgs, "the middleware logged nothing"
    assert any(
        m.startswith("method=GET") and "/api/v1/auth/me" in m for m in msgs
    ), msgs


# ---------------------------------------------------------------------------
# T-M8-09 / MW-02 — duration is measured and recorded
# ---------------------------------------------------------------------------

def test_m8_09_measures_duration(client, world, caplog):
    with caplog.at_level(logging.INFO, logger=LOG_NAME):
        client.get("/api/v1/health")
    msgs = logged_messages(caplog)
    assert any(
        m.startswith("method=GET") and re.search(r"duration_ms=\d+(\.\d+)?", m)
        for m in msgs
    ), msgs


# ---------------------------------------------------------------------------
# T-M8-10 / MW-03 — request ID propagation + no secrets in logs
# ---------------------------------------------------------------------------

def test_m8_10_request_id_propagated_and_echoed(client, world, caplog):
    with caplog.at_level(logging.INFO, logger=LOG_NAME):
        r = client.get(
            "/api/v1/auth/me",
            headers={**bearer(world.tok_customer), "X-Request-Id": "req-abc-123"},
        )
    assert r.status_code == 200
    # the client's id is propagated into the response …
    assert r.headers.get("X-Request-Id") == "req-abc-123"
    # … and into the log line
    assert any("request_id=req-abc-123" in m for m in logged_messages(caplog))
    # without a header, a fresh id is generated and echoed
    r2 = client.get("/api/v1/auth/me", headers=bearer(world.tok_customer))
    generated = r2.headers.get("X-Request-Id")
    assert generated and len(generated) == 32  # uuid4 hex


def test_m8_10_no_secrets_in_logs(client, world, caplog):
    token = world.tok_customer
    with caplog.at_level(logging.INFO, logger=LOG_NAME):
        # a real token on a protected request …
        client.get("/api/v1/auth/me", headers=bearer(token))
        # … and a password in a request body
        client.post("/api/v1/auth/login",
                    json={"email": "cust1@example.org",
                          "password": "Correct-Horse-99x"})
    msgs = logged_messages(caplog)
    assert msgs
    for m in msgs:
        assert token not in m          # no bearer tokens
        assert "Bearer" not in m       # no Authorization header text
        assert "Correct-Horse-99x" not in m  # no passwords
