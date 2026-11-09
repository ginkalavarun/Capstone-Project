"""M4 authentication & authorization tests (docs/test-plan.md §M4).

Scope note (honest layering): batch 2's protected surface is ``/auth/me``.
The *helpers* (current-user, role) are proven here against the real app
and a stub route; the full endpoint sweep (T-M4-14) and the
two-customer / two-owner / two-partner isolation tests (T-M4-15/16/17)
materialize as each protected feature lands in batches 3–6 — the batch-2
versions below pin the foundation they will be built on.
"""
import base64
import json
import logging
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from app.core import constants as C
from app.core import security
from app.core.config import ConfigError
from app.core.deps import build_get_current_user, build_require_roles
from app.core.errors import register_error_handlers
from app.db.engine import make_engine
from app.db.migrate import run_migrations
from app.db.models import User
from app.db.session import SessionFactory
from tests.conftest import UNIT_TEST_JWT_SECRET, make_test_settings

KNOWN_PASSWORD = "Correct-Horse-99x"


def make_user(db_session, email: str, role: str, password: str = KNOWN_PASSWORD,
              full_name: str = "Test User", active: bool = True) -> User:
    user = User(
        email=email,
        password_hash=security.hash_password(password),
        full_name=full_name,
        role=role,
        is_active=active,
    )
    db_session.add(user)
    db_session.commit()
    return user


def login_token(client, email: str, password: str = KNOWN_PASSWORD) -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# T-M4-01 / T-M4-02 — registration (AUTH-01)
# ---------------------------------------------------------------------------

def test_m4_01_register_creates_customer_then_login(client, db_session):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "NEW@EXAMPLE.COM", "password": KNOWN_PASSWORD, "full_name": "New Person"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["role"] == C.ROLE_CUSTOMER
    assert body["user"]["email"] == "new@example.com"  # normalized
    assert "password" not in json.dumps(body) and "password_hash" not in json.dumps(body)
    row = db_session.query(User).filter_by(email="new@example.com").first()
    assert row is not None and row.role == C.ROLE_CUSTOMER

    token = login_token(client, "new@example.com")
    me = client.get("/api/v1/auth/me", headers=bearer(token))
    assert me.status_code == 200
    assert me.json()["email"] == "new@example.com"


def test_m4_01_duplicate_email_409(client, db_session):
    payload = {"email": "dup@example.org", "password": KNOWN_PASSWORD, "full_name": "D"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    r = client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 409
    assert r.json()["code"] == "EMAIL_TAKEN"
    assert db_session.query(User).filter_by(email="dup@example.org").count() == 1


@pytest.mark.parametrize("role", ["restaurant_owner", "delivery_partner", "owner"])
def test_m4_02_privileged_role_request_rejected(client, db_session, role):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": f"evil-{role}@example.org", "password": KNOWN_PASSWORD,
              "full_name": "E", "role": role},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"
    assert db_session.query(User).filter(
        User.email == f"evil-{role}@example.org"
    ).first() is None  # no partial account


# ---------------------------------------------------------------------------
# T-M4-03 / T-M4-07 — login & deactivation (AUTH-02, AUTH-05)
# ---------------------------------------------------------------------------

def test_m4_03_login_happy_and_uniform_sad(client, db_session):
    make_user(db_session, "login1@example.org", C.ROLE_CUSTOMER)
    ok = client.post("/api/v1/auth/login", json={"email": "login1@example.org", "password": KNOWN_PASSWORD})
    assert ok.status_code == 200
    assert ok.json()["token_type"] == "bearer"
    assert ok.json()["user"]["email"] == "login1@example.org"

    wrong = client.post("/api/v1/auth/login", json={"email": "login1@example.org", "password": "nope-nope-1"})
    assert wrong.status_code == 401 and wrong.json()["code"] == "INVALID_CREDENTIALS"

    ghost = client.post("/api/v1/auth/login", json={"email": "ghost@example.org", "password": KNOWN_PASSWORD})
    assert ghost.status_code == 401 and ghost.json()["code"] == "INVALID_CREDENTIALS"  # uniform


def test_m4_07_deactivated_user_denied_with_valid_token(client, db_session):
    user = make_user(db_session, "off@example.org", C.ROLE_CUSTOMER)
    token = login_token(client, "off@example.org")
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 200
    user.is_active = False
    db_session.commit()
    r = client.get("/api/v1/auth/me", headers=bearer(token))
    assert r.status_code == 401
    assert r.json()["code"] == "USER_INACTIVE"


# ---------------------------------------------------------------------------
# T-M4-04 / T-M4-05 / T-M4-06 / T-M4-19 — tokens (AUTH-03, AUTH-04, D4)
# ---------------------------------------------------------------------------

def test_m4_04_stored_hash_is_bcrypt(client, db_session):
    client.post("/api/v1/auth/register", json={"email": "bc@example.org", "password": KNOWN_PASSWORD, "full_name": "B"})
    row = db_session.query(User).filter_by(email="bc@example.org").first()
    assert row.password_hash.startswith("$2b$")  # bcrypt 4.x default
    assert security.verify_password(KNOWN_PASSWORD, row.password_hash)
    assert not security.verify_password("wrong-pass-123", row.password_hash)


def test_m4_05_jwt_shape_and_tampered_signature(client, db_session):
    make_user(db_session, "jwt1@example.org", C.ROLE_CUSTOMER, full_name="Jwt One")
    row = db_session.query(User).filter_by(email="jwt1@example.org").first()
    token = login_token(client, "jwt1@example.org")
    claims = pyjwt.decode(token, UNIT_TEST_JWT_SECRET, algorithms=["HS256"])
    assert claims["sub"] == str(row.id)  # stable user id as subject (D4)
    assert claims["type"] == "access" and "exp" in claims and "iat" in claims
    # tamper the signature → 401
    h, p, s = token.split(".")
    tampered = f"{h}.{p}{'A' if s[-1] != 'A' else 'B'}"
    r = client.get("/api/v1/auth/me", headers=bearer(tampered))
    assert r.status_code == 401 and r.json()["code"] == "TOKEN_INVALID"


def test_m4_06_alg_none_and_foreign_alg_rejected(client, db_session):
    user = make_user(db_session, "alg@example.org", C.ROLE_CUSTOMER)
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "exp": now + timedelta(minutes=5), "iat": now, "type": "access"}
    # alg=none token (unsigned) must be refused by the HS256 allowlist
    none_token = pyjwt.encode(payload, "", algorithm="none")
    r = client.get("/api/v1/auth/me", headers=bearer(none_token))
    assert r.status_code == 401 and r.json()["code"] == "TOKEN_INVALID"
    # token whose header claims RS256 must also be refused
    good = pyjwt.encode(payload, UNIT_TEST_JWT_SECRET, algorithm="HS256")
    gh, gp, gs = good.split(".")
    forged_header = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    r = client.get("/api/v1/auth/me", headers=bearer(f"{forged_header}.{gp}.{gs}"))
    assert r.status_code == 401 and r.json()["code"] == "TOKEN_INVALID"


def test_m4_19_expired_token_rejected(client, db_session):
    user = make_user(db_session, "exp@example.org", C.ROLE_CUSTOMER)
    now = datetime.now(timezone.utc)
    expired = pyjwt.encode(
        {"sub": str(user.id), "exp": now - timedelta(minutes=1),
         "iat": now - timedelta(minutes=61), "type": "access"},
        UNIT_TEST_JWT_SECRET, algorithm="HS256",
    )
    r = client.get("/api/v1/auth/me", headers=bearer(expired))
    assert r.status_code == 401
    assert r.json()["code"] == "TOKEN_EXPIRED"


# ---------------------------------------------------------------------------
# T-M4-08 — startup guard (AUTH-06)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "secret",
    ["", "change-me", "dev-secret", "secret", "123456789012345"],  # last: 15 bytes, too short
)
def test_m4_08_startup_guard_refuses_unsafe_secret(secret):
    settings = make_test_settings("sqlite:////tmp/never-created-gate-test.db", jwt_secret=secret)
    with pytest.raises(ConfigError):
        settings.validate()


def test_m4_08_safe_secret_passes_guard():
    settings = make_test_settings("sqlite:////tmp/never-created-gate-test.db", jwt_secret="a" * 32)
    settings.validate()  # must not raise


# ---------------------------------------------------------------------------
# T-M4-09 — password byte policy (AUTH-07)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "password",
    [
        "short7",     # 6 bytes < 8
        "x" * 73,     # 73 bytes > 72 (bcrypt hard limit)
        "é" * 72,     # 72 chars but 144 bytes — must fail, never truncate
    ],
)
def test_m4_09_password_policy_rejects(client, password):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": f"pw{len(password)}x@example.org", "password": password, "full_name": "P"},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "PASSWORD_POLICY"


def test_m4_09_72_byte_password_accepted(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "max@example.org", "password": "x" * 72, "full_name": "Max"},
    )
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# T-M4-10 — no secrets in logs (D4 / D23)
# ---------------------------------------------------------------------------

def test_m4_10_no_tokens_or_passwords_in_logs(client, db_session, caplog):
    client.post("/api/v1/auth/register",
                json={"email": "logs@example.org", "password": KNOWN_PASSWORD, "full_name": "L"})
    token = login_token(client, "logs@example.org")
    with caplog.at_level(logging.DEBUG, logger="campusbite"):
        r = client.get("/api/v1/auth/me", headers=bearer(token))
    assert r.status_code == 200
    assert token not in caplog.text
    assert KNOWN_PASSWORD not in caplog.text
    assert "Authorization" not in caplog.text  # header values/names never logged


# ---------------------------------------------------------------------------
# T-M4-11 / T-M4-14 / T-M4-15 — /me, sweep, token binding (AUTH-09, AUTHZ-01/02)
# ---------------------------------------------------------------------------

def test_m4_11_me_for_each_role_and_401_without_token(client, db_session):
    for role, email in (
        (C.ROLE_CUSTOMER, "role-c@example.org"),
        (C.ROLE_OWNER, "role-o@example.org"),
        (C.ROLE_PARTNER, "role-p@example.org"),
    ):
        make_user(db_session, email, role)
        token = login_token(client, email)
        me = client.get("/api/v1/auth/me", headers=bearer(token))
        assert me.status_code == 200, me.text
        assert me.json()["role"] == role
    # no token at all
    assert client.get("/api/v1/auth/me").status_code == 401
    # garbage token
    r = client.get("/api/v1/auth/me", headers=bearer("not.a.jwt"))
    assert r.status_code == 401


def test_m4_14_protected_surface_sweep_batch2(client, db_session):
    """Batch-2 sweep: the only protected endpoint is /auth/me.

    The *full* matrix (every protected endpoint × no-token/401,
    role/403, ownership/404) extends here as features land in batches 3–6.
    """
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401  # unauthenticated
    # public endpoints must NOT demand auth
    assert client.get("/api/v1/health").status_code == 200


def test_m4_15_token_binding_two_customers(client, db_session):
    """Batch-2 half of T-M4-15: a token is bound to exactly one user.
    (Cross-*resource* isolation lands with the order endpoints, batch 4.)"""
    make_user(db_session, "cust-a@example.org", C.ROLE_CUSTOMER, full_name="Cust A")
    make_user(db_session, "cust-b@example.org", C.ROLE_CUSTOMER, full_name="Cust B")
    ta = login_token(client, "cust-a@example.org")
    tb = login_token(client, "cust-b@example.org")
    assert client.get("/api/v1/auth/me", headers=bearer(ta)).json()["email"] == "cust-a@example.org"
    assert client.get("/api/v1/auth/me", headers=bearer(tb)).json()["email"] == "cust-b@example.org"


# ---------------------------------------------------------------------------
# T-M4-18 — status-code policy for the helpers (AUTHZ-06)
# ---------------------------------------------------------------------------

def test_m4_18_role_403_and_auth_401_via_production_helpers(tmp_path):
    """The reusable helpers, exactly as later features will wire them,
    against a stub route (owner-only) on a real (temporary) database.

    Batch 2 pins the 401/403 axis; the ownership-failure → 404 axis
    materializes with the first owned resource (batches 3/4).
    """
    url = f"sqlite:///{tmp_path / 'authz.db'}"
    settings = make_test_settings(url)
    engine = make_engine(url)
    run_migrations(url)
    factory = SessionFactory(engine)

    app = FastAPI()
    register_error_handlers(app)  # same error contract as the production app
    get_current_user = build_get_current_user(factory, settings)
    owner_only = build_require_roles(get_current_user, C.ROLE_OWNER)

    @app.get("/api/v1/stub/owner-action")
    def stub(user=Depends(owner_only)):
        return {"role": user.role}

    s = factory.create()
    owner = make_user(s, "own-stub@example.org", C.ROLE_OWNER)
    customer = make_user(s, "cust-stub@example.org", C.ROLE_CUSTOMER)
    s.close()

    test_client = TestClient(app)
    # unauthenticated → 401
    r = test_client.get("/api/v1/stub/owner-action")
    assert r.status_code == 401
    # authenticated but wrong role → 403 (not 404, not 200)
    token = security.create_access_token(customer.id, settings.jwt_secret, 60)
    r = test_client.get("/api/v1/stub/owner-action", headers=bearer(token))
    assert r.status_code == 403 and r.json()["code"] == "ROLE_FORBIDDEN"
    # correct role → allowed
    token = security.create_access_token(owner.id, settings.jwt_secret, 60)
    r = test_client.get("/api/v1/stub/owner-action", headers=bearer(token))
    assert r.status_code == 200 and r.json()["role"] == C.ROLE_OWNER
    engine.dispose()


# ---------------------------------------------------------------------------
# T-M4-12 / T-M4-13 — provisioning CLI (AUTH-10, D2)
# ---------------------------------------------------------------------------

def test_m4_12_provision_owner_and_restaurant(tmp_path):
    from app.provision import provision_owner

    url = f"sqlite:///{tmp_path / 'prov.db'}"
    result = provision_owner(
        url, "owner-cli@example.org", "Cli Owner", "Cli Bites", "7 Test Way",
        fee_cents=150, password="Owner-Pass-9x!",
    )
    assert result["created"] is True
    assert result["password"] == "Owner-Pass-9x!"  # explicit input respected, not replaced
    engine = make_engine(url)
    s = SessionFactory(engine).create()
    owner = s.query(User).filter_by(email="owner-cli@example.org").first()
    assert owner is not None and owner.role == C.ROLE_OWNER
    assert owner.restaurant is not None and owner.restaurant.delivery_fee_cents == 150
    # idempotent re-run: 1:1 rule (D24) — existing restaurant reused, no duplicates
    result2 = provision_owner(
        url, "owner-cli@example.org", "Cli Owner", "Different Name", "7 Test Way",
        fee_cents=150, password="Owner-Pass-9x!",
    )
    assert result2["created"] is False
    assert s.query(User).filter_by(email="owner-cli@example.org").count() == 1
    assert s.query(User).count() == 1
    s.close()
    engine.dispose()


def test_m4_12_provisioning_failure_rolls_back_owner(tmp_path, monkeypatch):
    """If anything in the owner+restaurant transaction blows up, NEITHER row
    may exist (D2) — same guarantee as T-M3-19, at the service boundary."""
    import app.provision as provision_mod
    from app.provision import provision_owner

    def boom(_plain):
        raise RuntimeError("simulated bcrypt failure")

    monkeypatch.setattr(provision_mod, "hash_password", boom)
    url = f"sqlite:///{tmp_path / 'prov-fail.db'}"
    with pytest.raises(RuntimeError):
        provision_owner(url, "fail@example.org", "Fail Owner", "Fail Bites", "x",
                        password="Owner-Pass-9x!")
    engine = make_engine(url)
    s = SessionFactory(engine).create()
    assert s.query(User).count() == 0
    s.close()
    engine.dispose()


def test_m4_13_provision_partner_no_shared_defaults(tmp_path):
    from app.provision import provision_partner

    url = f"sqlite:///{tmp_path / 'prov-p.db'}"
    # no --password, non-TTY → a random one is generated and returned once
    result = provision_partner(url, "dp-cli@example.org", "Cli Partner")
    assert result["created"] is True
    assert result["role"] == C.ROLE_PARTNER
    assert len(result["password"]) >= 8  # passes the 8-byte minimum
    assert result["password"] not in {"password", "changeme", "Partner-Pass-1"}  # no shared default
    engine = make_engine(url)
    s = SessionFactory(engine).create()
    dp = s.query(User).filter_by(email="dp-cli@example.org").first()
    assert dp is not None and dp.is_active and security.verify_password(result["password"], dp.password_hash)
    s.close()
    engine.dispose()
