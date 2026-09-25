from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (and `backend/.env` locally)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Exact browser origin allowed by CORS. A single explicit origin, never "*".
    frontend_origin: str = "http://localhost:5173"
    # Not needed by the health endpoint; only database code and Alembic require it.
    database_url: str | None = None

    @field_validator("frontend_origin")
    @classmethod
    def _validate_origin(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")) or value.endswith("/"):
            raise ValueError("FRONTEND_ORIGIN must be an http(s) origin without a trailing slash")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
