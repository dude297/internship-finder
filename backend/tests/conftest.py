import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings

# Tests control configuration explicitly. Done at import time, before test modules import
# app.main (which builds the app from settings), so a developer's backend/.env or shell
# variables can't change test results. The app itself still loads backend/.env normally.
Settings.model_config["env_file"] = None
for _name in Settings.model_fields:
    os.environ.pop(_name.upper(), None)


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- PostgreSQL integration tests -------------------------------------------------------------
# Tests marked `postgres` need TEST_DATABASE_URL (a disposable database; tests migrate it up and
# down). Locally they skip without it. In CI (CI=true) a missing URL fails instead of skipping.

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def alembic_config(url: str) -> Config:
    config = Config()  # no ini file: keeps Alembic from reconfiguring pytest's logging
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def pg_url() -> str:
    if not TEST_DATABASE_URL:
        if os.environ.get("CI"):
            pytest.fail("TEST_DATABASE_URL must be set in CI; PostgreSQL tests may not skip")
        pytest.skip("TEST_DATABASE_URL not set")
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def pg_engine(pg_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(pg_url), "head")
    engine = create_engine(pg_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(pg_engine: Engine) -> Iterator[Session]:
    """A session inside a transaction that is rolled back after the test."""
    with pg_engine.connect() as connection, connection.begin() as transaction:
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        transaction.rollback()
