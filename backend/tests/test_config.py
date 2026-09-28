from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, normalize_database_url
from app.db import session


def test_tests_ignore_local_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("SESSION_COOKIE_SECURE=false\nDATABASE_URL=x\n")
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.session_cookie_secure is True
    assert settings.database_url is None


def test_defaults_are_secure() -> None:
    settings = Settings()

    assert settings.session_cookie_secure is True
    assert settings.session_ttl_hours == 24


def test_loads_values_from_dotenv_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SESSION_TTL_HOURS=2\nDATABASE_URL=postgresql://h/db\n")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)

    settings = Settings()

    assert settings.session_ttl_hours == 2
    assert settings.database_url == "postgresql://h/db"


def test_environment_overrides_dotenv_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SESSION_COOKIE_SECURE=true\n")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")

    assert Settings().session_cookie_secure is False


@pytest.mark.parametrize("hours", [0, -1, 24 * 31])
def test_rejects_unreasonable_session_ttl(hours: int) -> None:
    with pytest.raises(ValidationError):
        Settings(session_ttl_hours=hours)


def test_engine_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session, "get_settings", lambda: Settings(database_url=None))
    session.get_engine.cache_clear()

    with pytest.raises(RuntimeError, match="DATABASE_URL is not configured"):
        session.get_engine()


# --- DATABASE_URL normalization (ADR-009 §9). Synthetic credentials only. -------------------


@pytest.mark.parametrize("scheme", ["postgresql", "postgres"])
def test_plain_postgres_url_gets_the_psycopg_driver(scheme: str) -> None:
    url = f"{scheme}://user:pw@db.example.test:5432/app"

    assert normalize_database_url(url) == "postgresql+psycopg://user:pw@db.example.test:5432/app"


def test_psycopg_url_is_unchanged() -> None:
    url = "postgresql+psycopg://user:pw@db.example.test/app?sslmode=require"

    assert normalize_database_url(url) == url


def test_everything_after_the_scheme_is_preserved() -> None:
    rest = (
        "//synthetic%40user:p%2Fa%3As%23s%25w0rd@ep-example-123.us-west-2.aws.neon.test:5433"
        "/internship_finder?sslmode=require&channel_binding=require"
    )

    assert normalize_database_url("postgresql:" + rest) == "postgresql+psycopg:" + rest


@pytest.mark.parametrize(
    "url",
    [
        "mysql://user:synthetic-secret@h/db",
        "sqlite:///local.db",
        "postgresql+psycopg2://user:synthetic-secret@h/db",
        "postgresql+asyncpg://user:synthetic-secret@h/db",
        "http://user:synthetic-secret@h/db",
        "",
    ],
)
def test_unsupported_schemes_are_rejected_without_echoing_the_url(url: str) -> None:
    with pytest.raises(ValueError) as error:
        normalize_database_url(url)

    assert "synthetic-secret" not in str(error.value)


def test_runtime_and_alembic_share_the_normalized_url() -> None:
    settings = Settings(database_url="postgresql://u:p@h/db?sslmode=require")

    assert settings.database_url_for_driver() == "postgresql+psycopg://u:p@h/db?sslmode=require"


def test_engine_uses_the_normalized_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        session, "get_settings", lambda: Settings(database_url="postgresql://u:p@h/db")
    )
    session.get_engine.cache_clear()
    try:
        engine = session.get_engine()
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.pool._pre_ping  # type: ignore[attr-defined]
    finally:
        session.get_engine.cache_clear()


# --- Hosted mode and the proxy secret ---------------------------------------------------------


def test_hosted_requires_secure_cookies() -> None:
    with pytest.raises(ValidationError, match="SESSION_COOKIE_SECURE"):
        Settings(hosted=True, session_cookie_secure=False)
    assert Settings(hosted=True).hosted


def test_short_proxy_secret_is_rejected_without_echoing_it() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(proxy_shared_secret="synthetic-short")  # type: ignore[arg-type]

    assert "synthetic-short" not in str(error.value)


def test_proxy_secret_is_not_shown_in_repr() -> None:
    settings = Settings(proxy_shared_secret="s" * 40)  # type: ignore[arg-type]

    assert "s" * 40 not in repr(settings)
