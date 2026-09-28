"""The Alembic migrations against real PostgreSQL: up, down, up again, and no model drift."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

from app.models import Base
from tests.conftest import alembic_config

pytestmark = pytest.mark.postgres

MILESTONE_1_TABLES = {
    "profiles",
    "profile_sources",
    "profile_facts",
    "opportunities",
    "opportunity_source_records",
    "opportunity_requirements",
    "opportunity_evaluations",
    "eligibility_rule_results",
}
MILESTONE_1_REVISION = "3b9c6b57bb60"
MILESTONE_2_REVISION = "7d7f4f8b9a3c"
MILESTONE_2_TABLES = MILESTONE_1_TABLES | {"auth_users", "auth_sessions", "applications"}
TABLES = MILESTONE_2_TABLES | {
    "ingestion_sources",
    "ingestion_runs",
    "ingestion_run_errors",
    "opportunity_identifiers",
}
GRADUATION_CHECK = "ck_profiles_graduation_after_status_as_of"
MILESTONE_3_REVISION = "726372d627b8"
RUNNING_INDEX = "uq_ingestion_runs_one_running_per_source"


def tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def profile_checks(engine: Engine) -> set[str]:
    return {str(c["name"]) for c in inspect(engine).get_check_constraints("profiles")}


def running_index_definition(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return connection.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
            {"name": RUNNING_INDEX},
        )


def insert_running_runs(engine: Engine, count: int) -> None:
    with engine.begin() as connection:
        for _ in range(count):
            connection.execute(
                text(
                    "INSERT INTO ingestion_runs (id, source_id, status, started_at)"
                    " SELECT gen_random_uuid(), id, 'running', now() FROM ingestion_sources"
                )
            )


def test_upgrade_downgrade_upgrade(pg_engine: Engine, pg_url: str) -> None:
    config = alembic_config(pg_url)
    assert tables(pg_engine) == TABLES  # pg_engine migrated to head
    assert GRADUATION_CHECK in profile_checks(pg_engine)
    assert running_index_definition(pg_engine) is not None

    command.downgrade(config, MILESTONE_3_REVISION)
    # Asymmetric on purpose: the index belongs to 726372d627b8's intended schema.
    assert running_index_definition(pg_engine) is not None

    command.downgrade(config, MILESTONE_2_REVISION)
    assert tables(pg_engine) == MILESTONE_2_TABLES
    # Asymmetric on purpose: the constraint belongs to 7d7f4f8b9a3c's intended schema.
    assert GRADUATION_CHECK in profile_checks(pg_engine)

    command.downgrade(config, MILESTONE_1_REVISION)
    assert tables(pg_engine) == MILESTONE_1_TABLES
    assert GRADUATION_CHECK not in profile_checks(pg_engine)

    command.downgrade(config, "base")
    assert tables(pg_engine) == set()

    command.upgrade(config, MILESTONE_1_REVISION)
    assert tables(pg_engine) == MILESTONE_1_TABLES
    command.upgrade(config, MILESTONE_2_REVISION)
    assert tables(pg_engine) == MILESTONE_2_TABLES

    command.upgrade(config, "head")
    assert tables(pg_engine) == TABLES


def test_stale_milestone_2_database_gets_the_graduation_check(
    pg_engine: Engine, pg_url: str
) -> None:
    """A database migrated with the pre-merge local 7d7f4f8b9a3c reports that revision but lacks
    the constraint. Upgrading to head restores it without manual SQL."""
    config = alembic_config(pg_url)
    command.downgrade(config, MILESTONE_2_REVISION)
    with pg_engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE profiles DROP CONSTRAINT {GRADUATION_CHECK}"))
    assert GRADUATION_CHECK not in profile_checks(pg_engine)

    command.upgrade(config, "head")

    assert GRADUATION_CHECK in profile_checks(pg_engine)
    with pg_engine.connect() as connection:
        definition = connection.scalar(
            text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :name"),
            {"name": GRADUATION_CHECK},
        )
    assert "expected_graduation_date > education_status_as_of" in str(definition)


def test_stale_milestone_3_database_gets_the_running_index(pg_engine: Engine, pg_url: str) -> None:
    """A database migrated with the pre-merge local 726372d627b8 reports that revision but lacks
    the partial unique index. Upgrading to head restores it; one running run per source is fine."""
    config = alembic_config(pg_url)
    command.downgrade(config, MILESTONE_3_REVISION)
    with pg_engine.begin() as connection:
        connection.execute(text(f"DROP INDEX {RUNNING_INDEX}"))
    insert_running_runs(pg_engine, 1)

    command.upgrade(config, "head")

    definition = str(running_index_definition(pg_engine))
    assert "CREATE UNIQUE INDEX" in definition
    assert "(source_id) WHERE" in definition and "'running'" in definition
    with pg_engine.begin() as connection:
        connection.execute(text("DELETE FROM ingestion_runs"))


def test_running_index_reconciliation_refuses_duplicate_running_runs(
    pg_engine: Engine, pg_url: str
) -> None:
    config = alembic_config(pg_url)
    command.downgrade(config, MILESTONE_3_REVISION)
    with pg_engine.begin() as connection:
        connection.execute(text(f"DROP INDEX {RUNNING_INDEX}"))
    insert_running_runs(pg_engine, 2)

    with pytest.raises(RuntimeError, match="more than one run with status 'running'"):
        command.upgrade(config, "head")

    with pg_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ingestion_runs")) == 2  # untouched
        connection.execute(text("DELETE FROM ingestion_runs"))
    command.upgrade(config, "head")
    assert running_index_definition(pg_engine) is not None


def test_upgrade_backfills_curation_and_seeds_the_builtin_feed(
    pg_engine: Engine, pg_url: str
) -> None:
    config = alembic_config(pg_url)
    command.downgrade(config, MILESTONE_2_REVISION)
    with pg_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO opportunities (id, title, organization, opportunity_type)"
                " VALUES (gen_random_uuid(), 'Synthetic Manual Program', 'Example Institute',"
                " 'research')"
            )
        )

    command.upgrade(config, "head")

    with pg_engine.begin() as connection:
        curated = connection.execute(
            text("SELECT manually_curated_at = updated_at FROM opportunities")
        ).scalar_one()
        sources = connection.execute(
            text("SELECT kind, identifier, region, enabled FROM ingestion_sources")
        ).all()
        connection.execute(text("DELETE FROM opportunities"))
    assert curated is True
    assert [tuple(row) for row in sources] == [
        ("community_feed", "zshah-tech-internships", None, True)
    ]


def test_requirements_assessment_column_in_migration(pg_engine: Engine) -> None:
    inspector = inspect(pg_engine)
    column = next(
        c
        for c in inspector.get_columns("opportunities")
        if c["name"] == "requirements_assessment_status"
    )
    checks = {c["name"]: c["sqltext"] for c in inspector.get_check_constraints("opportunities")}

    assert column["nullable"] is False
    assert "unassessed" in str(column["default"])
    check = checks["ck_opportunities_requirements_assessment_status"]
    assert all(value in check for value in ("'unassessed'", "'partial'", "'complete'"))


def test_models_match_migrations(pg_engine: Engine) -> None:
    with pg_engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert diff == []
