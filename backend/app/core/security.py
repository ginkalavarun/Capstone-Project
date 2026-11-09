"""Password hashing (bcrypt directly, D4) and JWT issue/verify (PyJWT, D4).

Security rules honored here:
- bcrypt is used **directly** (not passlib). bcrypt's effective input limit
  is 72 bytes: we validate and **fail loudly** instead of silently
  truncating (AUTH-07).
- HS256 is the only accepted algorithm; `alg: none` and other algorithms are
  rejected by passing an explicit allowlist to `jwt.decode` (AUTH-04).
- `exp` is always written and always validated (AUTH-04).
- The token subject is the stable user id (string).
- Nothing in this module ever logs a password or a token (AUTH-08).
"""
import jwt
from datetime import datetime, timedelta, timezone


class PasswordPolicyError(ValueError):
    """Password fails the explicit policy (min/max bytes)."""


def validate_password(plain: str, min_bytes: int = 8, max_bytes: int = 72) -> str:
    """Validate a plaintext password against the policy (D4, A3).

    Returns the password unchanged on success; raises PasswordPolicyError
    otherwise. The 72-byte maximum is bcrypt's hard input limit.
    """
    data = plain.encode("utf-8")
    if len(data) < min_bytes:
        raise PasswordPolicyError(
            f"Password must be at least {min_bytes} bytes (got {len(data)})."
        )
    if len(data) > max_bytes:
        raise PasswordPolicyError(
            f"Password exceeds {max_bytes} bytes (bcrypt's hard input limit). "
            f"Choose a shorter password."
        )
    return plain


def hash_password(plain: str) -> str:
    """Hash with bcrypt; returns the `$2b$...` string (60 chars)."""
    import bcrypt

    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time check; returns False on any mismatch."""
    import bcrypt

    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        # Malformed stored hash (should never happen) is a mismatch, not a crash.
        return False


def create_access_token(
    user_id: int,
    secret: str,
    expires_minutes: int,
    algorithm: str = "HS256",
) -> str:
    """Issue a short-lived access token. `sub` is the stable user id (D4)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "exp": now + timedelta(minutes=expires_minutes),
        "iat": now,
        "type": "access",
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str, secret: str, algorithm: str = "HS256") -> dict:
    """Verify signature + algorithm allowlist + expiration.

    Raises jwt.PyJWTError (any kind) on failure — callers map that to 401.
    """
    # `algorithms=` is the explicit allowlist: only HS256 is accepted;
    # `alg: none` and RS256-labeled tokens cannot pass (AUTH-06).
    claims = jwt.decode(
        token,
        secret,
        algorithms=[algorithm],
        options={"require": ["exp", "sub"]},
    )
    if claims.get("type") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return claims
