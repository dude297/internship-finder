from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (and `backend/.env` locally)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Not needed by the health endpoint; database code, the private API, and Alembic require it.
    database_url: str | None = None
    # Absolute lifetime of a login session (ADR-007).
    session_ttl_hours: int = Field(default=24, ge=1, le=24 * 30)
    # Keep true anywhere but plain-HTTP development on a non-localhost host (ADR-007 §4).
    session_cookie_secure: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
