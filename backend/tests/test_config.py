from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.db import session


def test_tests_ignore_local_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("FRONTEND_ORIGIN=https://local.example\nDATABASE_URL=x\n")
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.frontend_origin == "http://localhost:5173"
    assert settings.database_url is None


def test_loads_values_from_dotenv_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FRONTEND_ORIGIN=https://app.example\nDATABASE_URL=postgresql://h/db\n")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)

    settings = Settings()

    assert settings.frontend_origin == "https://app.example"
    assert settings.database_url == "postgresql://h/db"


def test_environment_overrides_dotenv_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FRONTEND_ORIGIN=https://dotenv.example\n")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://env.example")

    assert Settings().frontend_origin == "https://env.example"


@pytest.mark.parametrize("origin", ["*", "localhost:5173", "http://localhost:5173/"])
def test_rejects_unsafe_or_malformed_frontend_origin(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(frontend_origin=origin)


def test_engine_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session, "get_settings", lambda: Settings(database_url=None))
    session.get_engine.cache_clear()

    with pytest.raises(RuntimeError, match="DATABASE_URL is not configured"):
        session.get_engine()
