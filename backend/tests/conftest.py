import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.main import create_app
from app.models import AuthUser
from app.services.auth import create_owner

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
def db(pg_engine: Engine, request: pytest.FixtureRequest) -> Iterator[Session]:
    """A session inside a transaction that is rolled back after the test.

    The migration-seeded program registry source (ADR-014 §5) is removed inside that transaction
    unless the test is marked `registry`, so tests written for a single built-in source (the
    feed) keep their world; registry tests opt in."""
    with pg_engine.connect() as connection, connection.begin() as transaction:
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        if request.node.get_closest_marker("registry") is None:
            session.execute(text("DELETE FROM ingestion_sources WHERE kind = 'curated_registry'"))
        yield session
        session.close()
        transaction.rollback()


# --- API tests (PostgreSQL) --------------------------------------------------------------------
# Synthetic, test-only credentials. Never real ones.
OWNER_USERNAME = "synthetic-owner"
OWNER_PASSWORD = "synthetic-test-password"


@pytest.fixture
def anon_client(db: Session) -> Iterator[TestClient]:
    """The app with its database session replaced by the rolled-back test session.

    Like the real dependency, uncommitted work is rolled back when the request ends (in the
    test session that means back to the request's savepoint)."""

    def test_session() -> Iterator[Session]:
        try:
            yield db
        finally:
            db.rollback()

    app = create_app()
    app.dependency_overrides[get_session] = test_session
    # https so the Secure session cookie is sent back, as a browser would.
    with TestClient(app, base_url="https://testserver") as client:
        yield client


@pytest.fixture
def owner(db: Session) -> AuthUser:
    user = create_owner(db, OWNER_USERNAME, OWNER_PASSWORD)
    db.commit()
    return user


@pytest.fixture
def client(anon_client: TestClient, owner: AuthUser) -> TestClient:
    """Logged in as the synthetic owner, sending the CSRF header on every request."""
    response = anon_client.post(
        "/api/auth/login", json={"username": OWNER_USERNAME, "password": OWNER_PASSWORD}
    )
    assert response.status_code == 200, response.text
    anon_client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return anon_client
