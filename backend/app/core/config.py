from functools import lru_cache
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The runtime driver is psycopg 3. Neon (and most providers) hand out plain postgresql:// URLs.
_DRIVER_SCHEME = "postgresql+psycopg://"
_PLAIN_SCHEMES = ("postgresql://", "postgres://")


def normalize_database_url(url: str) -> str:
    """Point a PostgreSQL URL at psycopg 3, changing only the scheme.

    Credentials, host, port, database, and query (sslmode, channel_binding, ...) are kept
    byte for byte. Errors never include the URL, since it may contain a password."""
    if url.startswith(_DRIVER_SCHEME):
        return url
    for scheme in _PLAIN_SCHEMES:
        if url.startswith(scheme):
            return _DRIVER_SCHEME + url[len(scheme) :]
    raise ValueError(
        "DATABASE_URL must start with postgresql://, postgres://, or postgresql+psycopg://"
    )


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (and `backend/.env` locally)."""

    # hide_input_in_errors: a startup validation error must not print a secret or URL.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    # Not needed by the health endpoint; database code, the private API, and Alembic require it.
    # Read it through database_url_for_driver(), never log it.
    database_url: str | None = None
    # Absolute lifetime of a login session (ADR-007).
    session_ttl_hours: int = Field(default=24, ge=1, le=24 * 30)
    # Keep true anywhere but plain-HTTP development on a non-localhost host (ADR-007 §4).
    session_cookie_secure: bool = True
    # True on the hosted deployment (ADR-009): no public /docs, /redoc, /openapi.json, and
    # Secure cookies are mandatory.
    hosted: bool = False
    # Shared with Vercel's /api route, which sends it as X-IF-Proxy-Secret. Only requests that
    # carry it get a per-browser login-throttle key from X-Forwarded-For (ADR-009 §6).
    proxy_shared_secret: SecretStr | None = Field(default=None, min_length=32)
    # Test-only (E2E): serve ingestion responses from this JSON file ({url: body}) instead of
    # the network. Never set it outside disposable test environments.
    ingestion_fixture_file: str | None = None

    @model_validator(mode="after")
    def _hosted_needs_secure_cookies(self) -> Self:
        if self.hosted and not self.session_cookie_secure:
            raise ValueError("HOSTED=true requires SESSION_COOKIE_SECURE=true")
        return self

    def database_url_for_driver(self) -> str:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        return normalize_database_url(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
