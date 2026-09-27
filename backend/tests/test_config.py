from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
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
