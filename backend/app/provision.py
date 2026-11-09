"""Local provisioning CLI for privileged accounts (D2).

Public registration creates *customers only* (D2). Owners, their
restaurants, and delivery partners are created locally by the operator:

    python -m app.provision owner   --email sam@example.com \
        --name "Sam Kapoor" --restaurant "Slice House" \
        --address "10 Green Line, Block A" [--fee-cents 200] [--password ...]
    python -m app.provision partner --email dana@example.com --name "Dana Kim" [--password ...]

Rules honored here:
- **Owner + restaurant in ONE transaction** (D2): if the restaurant
  insert fails, the owner row is rolled back too — never a half state.
- One owner, at most one restaurant (D24): the CLI reuses the owner's
  existing restaurant instead of failing when it already has one.
- No shared default passwords: ``--password`` is optional; when omitted
  the CLI prefers interactive input (TTY) and otherwise generates a random
  one, printed **once** to the terminal (never committed, never logged).
- The database file is never created with privileged accounts by any
  other path (no public owner/partner endpoints exist — D2).
"""
import argparse
import getpass
import os
import secrets
import sys
from email.utils import parseaddr

from .core import constants as C
from .core.security import hash_password, validate_password
from .db.engine import make_engine
from .db.migrate import run_migrations
from .db.models import Restaurant, User
from .db.session import SessionFactory

DEFAULT_DB = "sqlite:///./data/campusbite.db"


def _normalize_email(raw: str) -> str:
    _, addr = parseaddr(raw)
    addr = addr.strip().lower()
    if "@" not in addr or "." not in addr.split("@")[-1]:
        raise SystemExit(f"error: {raw!r} is not a valid email address")
    return addr


def _get_password(explicit: str | None, label: str) -> str:
    if explicit:
        return validate_password(explicit)  # raises → 422-equivalent exit
    if sys.stdin.isatty():
        while True:
            pw = getpass.getpass(f"Choose a password for {label} (8–72 bytes): ")
            try:
                return validate_password(pw)
            except Exception as e:  # noqa: BLE001 — prompt again
                print(f"  {e}", file=sys.stderr)
    # Non-interactive fallback: generate, print once. Never a shared default (D2).
    return secrets.token_urlsafe(12)


def _open_session(database_url: str):
    run_migrations(database_url)
    engine = make_engine(database_url)
    return engine, SessionFactory(engine).create()


def provision_owner(
    database_url: str,
    email: str,
    full_name: str,
    restaurant_name: str,
    address: str,
    *,
    fee_cents: int = 200,
    password: str | None = None,
) -> dict:
    """Create an owner (+ their restaurant) atomically (D2)."""
    email = _normalize_email(email)
    password = password or _get_password(password, email)
    if fee_cents < 0:
        raise SystemExit("error: --fee-cents must be >= 0")
    engine, session = _open_session(database_url)
    try:
        owner = session.query(User).filter(User.email == email).first()
        if owner is None:
            owner = User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name.strip(),
                role=C.ROLE_OWNER,
                is_active=True,
            )
            session.add(owner)
            session.flush()
        elif owner.restaurant is not None:
            # Already provisioned, with a restaurant (D24: 1:1) — idempotent.
            print(f"{email} already has restaurant {owner.restaurant.name!r}; nothing to do.")
            return {"email": email, "role": owner.role, "restaurant": owner.restaurant.name,
                    "created": False}
        restaurant = session.query(Restaurant).filter(Restaurant.owner_id == owner.id).first()
        if restaurant is None:
            restaurant = Restaurant(
                owner_id=owner.id,
                name=restaurant_name.strip(),
                address=address.strip(),
                delivery_fee_cents=fee_cents,
            )
            session.add(restaurant)
        # One commit: both rows, or neither (D2).
        session.commit()
        return {
            "email": email,
            "password": password,
            "role": owner.role,
            "restaurant": restaurant.name,
            "created": True,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def provision_partner(
    database_url: str,
    email: str,
    full_name: str,
    *,
    password: str | None = None,
) -> dict:
    """Create (or idempotently reuse) an active delivery partner."""
    email = _normalize_email(email)
    password = password or _get_password(password, email)
    engine, session = _open_session(database_url)
    try:
        partner = session.query(User).filter(User.email == email).first()
        created = False
        if partner is None:
            partner = User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name.strip(),
                role=C.ROLE_PARTNER,
                is_active=True,
            )
            session.add(partner)
            created = True
        elif partner.role != C.ROLE_PARTNER:
            raise SystemExit(f"error: {email} exists with role {partner.role!r}; refusing to change it.")
        partner.is_active = True  # provisioning (re)activates
        session.commit()
        return {"email": email, "password": password, "role": partner.role, "created": created}
    except SystemExit:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def _resolve_database_url(explicit: str | None) -> str:
    return explicit or os.environ.get("DATABASE_URL") or DEFAULT_DB


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.provision",
        description="Create privileged local accounts (owners, delivery partners).",
    )
    parser.add_argument("--database-url", default=None, help="Defaults to $DATABASE_URL or ./data/campusbite.db")
    sub = parser.add_subparsers(dest="kind", required=True)

    owner = sub.add_parser("owner", help="create a restaurant owner + their restaurant")
    owner.add_argument("--email", required=True)
    owner.add_argument("--name", required=True, help="full name / display name")
    owner.add_argument("--restaurant", required=True, help="restaurant name")
    owner.add_argument("--address", required=True, help="restaurant address")
    owner.add_argument("--fee-cents", type=int, default=200, help="delivery fee in cents (default 200)")
    owner.add_argument("--password", default=None, help="or it will be prompted/generated")

    partner = sub.add_parser("partner", help="create a delivery partner")
    partner.add_argument("--email", required=True)
    partner.add_argument("--name", required=True, help="full name / display name")
    partner.add_argument("--password", default=None, help="or it will be prompted/generated")

    args = parser.parse_args(argv)
    database_url = _resolve_database_url(args.database_url)

    if args.kind == "owner":
        result = provision_owner(
            database_url, args.email, args.name, args.restaurant, args.address,
            fee_cents=args.fee_cents, password=args.password,
        )
    else:
        result = provision_partner(database_url, args.email, args.name, password=args.password)

    if result.get("created"):
        print(f"created {result['role']} {result['email']}")
        if "restaurant" in result and result["restaurant"]:
            print(f"  restaurant: {result['restaurant']}")
        print(f"  password (shown once, store it now): {result['password']}")
    else:
        print(f"already exists: {result['email']}")


if __name__ == "__main__":
    main()
