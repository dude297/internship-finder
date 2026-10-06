from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Created lazily so the app starts (and /api/health works) without DATABASE_URL."""
    return create_engine(
        get_settings().database_url_for_driver(),
        pool_pre_ping=True,
        # Never render bound parameters (profile-derived values) into error messages or logs.
        hide_parameters=True,
    )


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request. Nothing is committed implicitly: the route
    handler commits once after its service call, and anything uncommitted is rolled back when
    the session closes. Objects stay loaded after commit so responses can be built from them."""
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session
