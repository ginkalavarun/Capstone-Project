"""Authentication endpoints (batch 2; AUTH-01…09).

- ``POST /auth/register`` — **public**, creates a *customer* only (D2).
  An account with the email already exists → 409 ``EMAIL_TAKEN``.
- ``POST /auth/login`` — valid credentials → short-lived HS256 access token
  (PyJWT; ``exp`` always written/validated, D4) + the user profile.
  Wrong password / unknown email → uniform 401 ``INVALID_CREDENTIALS``
  (no user enumeration).
- ``GET /auth/me`` — the authenticated user's profile (any role).

The current user is **always** re-loaded from the database (AUTH-05): the
token only proves *which* user; the row decides whether they may act.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core import constants as C
from ...core import security
from ...core.config import Settings
from ...core.deps import build_get_current_user
from ...core.errors import ApiError
from ...db.models import User
from ...db.session import SessionFactory
from ...schemas.auth import LoginIn, RegisterIn, RegisterOut, TokenOut, UserOut


def build_auth_router(session_factory: SessionFactory, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])
    get_current_user = build_get_current_user(session_factory, settings)
    db_dep = Depends(session_factory.get)

    @router.post("/register", status_code=201, response_model=RegisterOut)
    def register(payload: RegisterIn, db: Session = db_dep) -> RegisterOut:
        email = str(payload.email).lower()  # EmailStr is already lowercase; keep the intent explicit
        if db.query(User).filter(User.email == email).first() is not None:
            raise ApiError(409, "EMAIL_TAKEN", "An account with this email already exists.")
        try:
            plain = security.validate_password(
                payload.password,
                settings.password_min_bytes,
                settings.password_max_bytes,
            )
        except security.PasswordPolicyError as e:
            raise ApiError(422, "PASSWORD_POLICY", str(e))
        user = User(
            email=email,
            password_hash=security.hash_password(plain),
            full_name=payload.full_name.strip(),
            role=C.ROLE_CUSTOMER,  # the ONLY role public registration can create (D2)
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return RegisterOut(user=UserOut.from_user(user))

    @router.post("/login", response_model=TokenOut)
    def login(payload: LoginIn, db: Session = db_dep) -> TokenOut:
        email = str(payload.email).lower()
        user = db.query(User).filter(User.email == email).first()
        # Uniform 401 for unknown email and wrong password (no enumeration).
        if user is None or not security.verify_password(payload.password, user.password_hash):
            raise ApiError(401, "INVALID_CREDENTIALS", "Incorrect email or password.")
        if not user.is_active:
            raise ApiError(401, "USER_INACTIVE", "This account is deactivated.")
        token = security.create_access_token(
            user.id, settings.jwt_secret, settings.jwt_expire_minutes, settings.jwt_algorithm
        )
        return TokenOut(access_token=token, user=UserOut.from_user(user))

    @router.get("/me", response_model=UserOut)
    def me(user: User = Depends(get_current_user)) -> UserOut:
        return UserOut.from_user(user)

    return router
