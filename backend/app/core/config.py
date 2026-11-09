"""Centralized, environment-driven configuration (pydantic-settings).

Secrets (D23): real values come from the environment — a local `.env` file in
development, injected at runtime in Docker. Nothing sensitive is ever stored
in code, images, or the repo. `.env.example` documents every variable.

Startup guard (D4): a missing, short, or known-placeholder `JWT_SECRET` makes
the app refuse to boot. The OpenAI key (D9) is deliberately optional: without
it the app starts and every non-AI feature works.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """Configuration is present but unsafe; the app must not start."""


# Values (lowercased) treated as "not a real secret" by the startup guard.
UNSAFE_JWT_SECRETS = {
    "",
    "change-me",
    "changeme",
    "change-me-generate-a-long-random-value",
    "placeholder",
    "secret",
    "jwt-secret",
    "dev-secret",
    "supersecret",
}


class Settings(BaseSettings):
    """Every knob of the application, overridable via environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- App / API (D14) ---
    app_name: str = "CampusBite API"
    api_base_path: str = "/api/v1"

    # --- Database (D1) ---
    # sqlite:///./relative  |  sqlite:////absolute  (four slashes = absolute)
    database_url: str = "sqlite:////data/campusbite.db"
    run_migrations_on_startup: bool = True  # D11; single-worker documented
    enable_sqlite_wal: bool = False  # N7: off by default, env-overridable

    # --- Auth (D4; A3/A4) ---
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"  # explicitly constrained; "none" never accepted
    jwt_expire_minutes: int = Field(default=60, ge=1, le=1440)
    password_min_bytes: int = Field(default=8, ge=4, le=64)
    password_max_bytes: int = Field(default=72, ge=8, le=72)  # bcrypt hard limit

    # --- CORS (D10): explicit allowlist, comma-separated; no wildcards ---
    cors_origins: str = "http://localhost:5173"

    # --- Reminder scanner (D6; A9) ---
    reminder_scanner_enabled: bool = True
    reminder_interval_seconds: int = Field(default=60, ge=1)
    reminder_stale_minutes: int = Field(default=15, ge=1)

    # --- AI insights (D9; A6/A7) ---
    openai_api_key: str | None = None  # optional at startup (D9)
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = Field(default=30.0, gt=0)
    ai_max_question_chars: int = Field(default=500, ge=1)
    ai_history_window: int = Field(default=50, ge=1)
    ai_rate_limit: int = Field(default=10, ge=1)
    ai_rate_window_minutes: int = Field(default=10, ge=1)

    # --- Money (D3, D26): single documented currency ---
    currency: str = "EUR"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.strip())

    def validate(self) -> None:
        """Fail fast on unsafe configuration (called once at startup)."""
        if self.jwt_secret.lower() in UNSAFE_JWT_SECRETS:
            raise ConfigError(
                "JWT_SECRET is missing or a known placeholder value. "
                "Generate one (e.g. `python -c \"import secrets; "
                "print(secrets.token_urlsafe(48))\"`) and set it in your "
                "environment. Refusing to start (D4)."
            )
        if len(self.jwt_secret.encode("utf-8")) < 16:
            raise ConfigError(
                f"JWT_SECRET must be at least 16 bytes (got "
                f"{len(self.jwt_secret.encode('utf-8'))}). Refusing to start (D4)."
            )
        if "*" in self.cors_origin_list:
            raise ConfigError(
                "Wildcard CORS origins are not allowed (D10). List explicit "
                "frontend origins in CORS_ORIGINS."
            )


@lru_cache
def get_settings() -> Settings:
    """Production entry point (uvicorn). Tests construct Settings directly."""
    settings = Settings()
    settings.validate()
    return settings
