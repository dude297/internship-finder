import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.db import session


@pytest.mark.parametrize("origin", ["*", "localhost:5173", "http://localhost:5173/"])
def test_rejects_unsafe_or_malformed_frontend_origin(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(frontend_origin=origin)


def test_engine_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session, "get_settings", lambda: Settings(database_url=None))
    session.get_engine.cache_clear()

    with pytest.raises(RuntimeError, match="DATABASE_URL is not configured"):
        session.get_engine()
