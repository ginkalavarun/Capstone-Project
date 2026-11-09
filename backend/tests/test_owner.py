"""M8 owner endpoint (batch 8): T-M8-12 — GET /api/v1/owner/restaurant.

Frontend enablement: the owner dashboard's menu-management page needs the
id of the restaurant it manages to call the menu endpoints with. One owner
has at most one restaurant (D24), so the endpoint simply returns the
caller's own. Authorization: role check first (403), then existence (404
for an owner whose provisioning left no restaurant).
"""
from app.core import constants as C
from tests.test_auth import login_token
from tests.test_lifecycle import bearer, make_restaurant, make_user


def test_own_restaurant_returns_callers_restaurant(client, db_session):
    owner1 = make_user(db_session, "own1@example.org", C.ROLE_OWNER, "Owner 1")
    owner2 = make_user(db_session, "own2@example.org", C.ROLE_OWNER, "Owner 2")
    rest1 = make_restaurant(db_session, owner1, "Alpha", fee=250)
    make_restaurant(db_session, owner2, "Beta", fee=350)
    db_session.commit()

    tok = login_token(client, "own1@example.org")
    resp = client.get("/api/v1/owner/restaurant", headers=bearer(tok))
    assert resp.status_code == 200
    d = resp.json()
    assert d["id"] == rest1.id
    assert d["name"] == "Alpha"
    assert d["delivery_fee_cents"] == 250


def test_own_restaurant_is_scoped_to_the_caller(client, db_session):
    """Each owner gets their own restaurant — never another owner's (D8)."""
    owner1 = make_user(db_session, "own1@example.org", C.ROLE_OWNER, "Owner 1")
    owner2 = make_user(db_session, "own2@example.org", C.ROLE_OWNER, "Owner 2")
    rest1 = make_restaurant(db_session, owner1, "Alpha", fee=250)
    rest2 = make_restaurant(db_session, owner2, "Beta", fee=350)
    db_session.commit()

    tok2 = login_token(client, "own2@example.org")
    d = client.get("/api/v1/owner/restaurant", headers=bearer(tok2)).json()
    assert d["id"] == rest2.id
    assert d["id"] != rest1.id
    assert d["name"] == "Beta"


def test_own_restaurant_rejects_non_owners(client, db_session):
    customer = make_user(db_session, "cust1@example.org", C.ROLE_CUSTOMER, "Cust")
    partner = make_user(db_session, "dp1@example.org", C.ROLE_PARTNER, "Partner")
    db_session.commit()

    resp = client.get("/api/v1/owner/restaurant",
                      headers=bearer(login_token(client, "cust1@example.org")))
    assert resp.status_code == 403
    assert resp.json()["code"] == "ROLE_FORBIDDEN"

    resp = client.get("/api/v1/owner/restaurant",
                      headers=bearer(login_token(client, "dp1@example.org")))
    assert resp.status_code == 403
    assert resp.json()["code"] == "ROLE_FORBIDDEN"


def test_own_restaurant_missing_for_provisioned_role_without_restaurant(client, db_session):
    """An owner role without a restaurant row → 404, not a 500."""
    make_user(db_session, "own1@example.org", C.ROLE_OWNER, "Owner 1")
    db_session.commit()

    resp = client.get("/api/v1/owner/restaurant",
                      headers=bearer(login_token(client, "own1@example.org")))
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_own_restaurant_requires_authentication(client, db_session):
    resp = client.get("/api/v1/owner/restaurant")
    assert resp.status_code == 401
