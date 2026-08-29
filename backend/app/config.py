import os

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-secret-change-me"  # a known-bad placeholder, never a real credential
MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = os.getenv("ENVIRONMENT", "development")
    """One of development | staging | production. Production applies stricter
    startup checks (see `validate_for_production`)."""

    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
    jwt_secret: str = os.getenv("JWT_SECRET", DEV_JWT_SECRET)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    adzuna_app_id: str = os.getenv("ADZUNA_APP_ID", "")
    adzuna_app_key: str = os.getenv("ADZUNA_APP_KEY", "")
    jooble_api_key: str = os.getenv("JOOBLE_API_KEY", "")

    # Greenhouse and Lever are per-company, not keyword-searchable: each hosts
    # one employer's board under a slug (e.g. "stripe"). Comma-separated, and
    # the connector is simply inactive when its list is empty -- the same
    # is_configured() contract the keyed connectors use.
    greenhouse_companies: str = os.getenv("GREENHOUSE_COMPANIES", "")
    lever_companies: str = os.getenv("LEVER_COMPANIES", "")

    cors_origins: str = os.getenv("CORS_ORIGINS", "*")

    # Login throttling: attempts allowed per window, per email+IP.
    login_rate_limit_attempts: int = int(os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "10"))
    login_rate_limit_window_seconds: int = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300"))

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


settings = Settings()

# Render (and most managed Postgres providers) hand out URLs starting with
# "postgres://", but SQLAlchemy's psycopg2 driver expects "postgresql://".
if settings.database_url.startswith("postgres://"):
    settings.database_url = settings.database_url.replace("postgres://", "postgresql://", 1)


def validate_for_production() -> list[str]:
    """Returns a list of fatal misconfigurations for a production deploy.

    Called at startup. Shipping with the default signing key would let anyone
    who has read the (public) repo mint valid tokens for any account, so this
    refuses to boot rather than coming up quietly insecure.
    """
    problems: list[str] = []

    if settings.jwt_secret == DEV_JWT_SECRET:
        problems.append(
            "JWT_SECRET is still the development placeholder. Anyone with the source "
            "could forge login tokens. Set it to a long random value."
        )
    elif len(settings.jwt_secret) < MIN_SECRET_LENGTH:
        problems.append(
            f"JWT_SECRET is only {len(settings.jwt_secret)} characters; use at least {MIN_SECRET_LENGTH}."
        )

    if settings.database_url.startswith("sqlite"):
        problems.append(
            "DATABASE_URL points at SQLite. Production runs on an ephemeral "
            "filesystem, so data would be lost on every deploy."
        )

    return problems
