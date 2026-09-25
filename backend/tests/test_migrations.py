"""The Alembic migrations against real PostgreSQL: up, down, up again, and no model drift."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from app.models import Base
from tests.conftest import alembic_config

pytestmark = pytest.mark.postgres

TABLES = {
    "profiles",
    "profile_sources",
    "profile_facts",
    "opportunities",
    "opportunity_source_records",
    "opportunity_requirements",
    "opportunity_evaluations",
    "eligibility_rule_results",
}


def tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def test_upgrade_downgrade_upgrade(pg_engine: Engine, pg_url: str) -> None:
    config = alembic_config(pg_url)
    assert tables(pg_engine) == TABLES  # pg_engine migrated to head

    command.downgrade(config, "base")
    assert tables(pg_engine) == set()

    command.upgrade(config, "head")
    assert tables(pg_engine) == TABLES


def test_models_match_migrations(pg_engine: Engine) -> None:
    with pg_engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert diff == []
