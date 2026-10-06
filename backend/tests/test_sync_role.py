"""The least-privilege sync role (ADR-027): scripts/sql/sync_role_grants.sql. Synthetic data only.

`test_every_table_is_granted_or_excluded` needs no database. The rest creates the role in the
disposable test database, applies the grants, and runs the scheduled sync connected AS the role.
"""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app import cli
from app.enums import (
    ExtractionMethod,
    FactCategory,
    FactReviewState,
    IngestionRunStatus,
    IngestionSourceKind,
    ProfileSourceKind,
)
from app.models import (
    Base,
    IngestionRun,
    IngestionSource,
    Opportunity,
    OpportunityEvaluation,
    Profile,
    ProfileFact,
)
from tests.ingestion_fixtures import (
    GREENHOUSE_BOARD,
    GREENHOUSE_URL,
    FakeSource,
    greenhouse_board,
    greenhouse_job,
)

SQL_FILE = Path(__file__).parents[2] / "scripts" / "sql" / "sync_role_grants.sql"
ROLE = "if_sync"
ROLE_PASSWORD = "synthetic-sync-role-password"  # test-only
GRANT = re.compile(r"^GRANT ([A-Z, ]+) ON TABLE (\w+) TO if_sync;$", re.MULTILINE)
EXCLUDED = re.compile(r"^-- excluded: (\w+): ", re.MULTILINE)
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE")


def granted() -> dict[str, set[str]]:
    return {
        table: {p.strip() for p in privileges.split(",")}
        for privileges, table in GRANT.findall(SQL_FILE.read_text())
    }


def excluded() -> set[str]:
    return set(EXCLUDED.findall(SQL_FILE.read_text()))


def test_every_table_is_granted_or_excluded() -> None:
    # A new table must be reviewed: granted to the sync role, or explicitly excluded, in
    # scripts/sql/sync_role_grants.sql. Otherwise the sync silently breaks or is over-granted.
    tables = set(Base.metadata.tables) | {"alembic_version"}
    listed = set(granted())
    assert listed.isdisjoint(excluded())
    assert tables == listed | excluded(), (
        f"unreviewed: {sorted(tables - listed - excluded())}; "
        f"stale: {sorted((listed | excluded()) - tables)}"
    )


def test_sensitive_tables_are_never_granted() -> None:
    assert {"auth_users", "auth_sessions", "profile_sources", "profile_source_artifacts"} | {
        "applications"
    } <= excluded()


@pytest.fixture
def sync_role(pg_engine: Engine) -> Iterator[Engine]:
    """The role, created and granted by the owner connection; an engine connected as the role.
    Everything is undone afterwards (the committed rows too), because other tests expect the
    migrated database to be empty."""
    with pg_engine.connect() as owner:
        sources = owner.execute(
            text(
                "SELECT id, enabled, etag, last_modified, last_success_at, last_attempted_at"
                " FROM ingestion_sources"
            )
        ).all()
        owner.exec_driver_sql(  # a leftover role from an aborted run
            f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{ROLE}') THEN"
            f" DROP OWNED BY {ROLE}; DROP ROLE {ROLE}; END IF; END $$"
        )
        owner.commit()
    with pg_engine.connect() as owner:
        owner.exec_driver_sql(SQL_FILE.read_text())
        owner.exec_driver_sql(f"ALTER ROLE {ROLE} PASSWORD '{ROLE_PASSWORD}'")
        owner.commit()
    url: URL = pg_engine.url.set(username=ROLE, password=ROLE_PASSWORD)
    engine = create_engine(url, hide_parameters=True)
    try:
        yield engine
    finally:
        engine.dispose()
        with pg_engine.connect() as owner:
            for statement in (
                "DELETE FROM opportunities",
                "DELETE FROM ingestion_runs",
                "DELETE FROM profiles",
                "DELETE FROM ingestion_sources WHERE kind = 'greenhouse'",
            ):
                owner.execute(text(statement))
            for row in sources:
                owner.execute(
                    text(
                        "UPDATE ingestion_sources SET enabled = :e, etag = :t, last_modified = :m,"
                        " last_success_at = :s, last_attempted_at = :a WHERE id = :i"
                    ),
                    {
                        "i": row.id,
                        "e": row.enabled,
                        "t": row.etag,
                        "m": row.last_modified,
                        "s": row.last_success_at,
                        "a": row.last_attempted_at,
                    },
                )
            owner.execute(text(f"DROP OWNED BY {ROLE}"))
            owner.execute(text(f"DROP ROLE {ROLE}"))
            owner.commit()


@pytest.mark.postgres
def test_grants_match_the_file_and_nothing_else(pg_engine: Engine, sync_role: Engine) -> None:
    expected = granted()
    with pg_engine.connect() as owner:
        tables = set(
            owner.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            .scalars()
            .all()
        )
        assert tables == set(expected) | excluded()  # also catches tables absent from the models
        for table in sorted(tables):
            held = {
                p
                for p in PRIVILEGES
                if owner.execute(
                    text("SELECT has_table_privilege(:r, :t, :p)"),
                    {"r": ROLE, "t": table, "p": p},
                ).scalar()
            }
            assert held == expected.get(table, set()), table
        attributes = owner.execute(
            text(
                "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls"
                " FROM pg_roles WHERE rolname = :r"
            ),
            {"r": ROLE},
        ).scalar()
        assert attributes is False
        # Idempotent: a second run changes nothing and doesn't fail.
        owner.exec_driver_sql(SQL_FILE.read_text())


@pytest.mark.postgres
def test_scheduled_sync_runs_as_the_role(
    pg_engine: Engine, sync_role: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(pg_engine) as owner:
        owner.execute(text("UPDATE ingestion_sources SET enabled = false"))
        owner.add(
            IngestionSource(
                kind=IngestionSourceKind.GREENHOUSE,
                identifier=GREENHOUSE_BOARD,
                display_name="Example Robotics",
            )
        )
        profile = Profile()
        profile.facts.append(
            ProfileFact(
                category=FactCategory.SKILL,
                fact_key="python",
                value={"name": "Python"},
                source_kind=ProfileSourceKind.MANUAL,
                extraction_method=ExtractionMethod.MANUAL,
                review_state=FactReviewState.ACCEPTED,
                verified_by_user=True,
            )
        )
        owner.add(profile)
        owner.commit()

    web = FakeSource()
    monkeypatch.setattr(cli, "get_engine", lambda: sync_role)
    monkeypatch.setattr(cli, "configured_transport", web.transport)
    requirement = "&lt;p&gt;Applicants must be at least 18 years old.&lt;/p&gt;"

    # Run 1 (partial, one invalid item): creates opportunities, identifiers, candidates,
    # evaluations, and an error row.
    web.json(
        GREENHOUSE_URL,
        greenhouse_board(
            greenhouse_job(1001, content=requirement),
            greenhouse_job(1002, title="Synthetic Hardware Intern"),
            greenhouse_job(1003, title=None),  # invalid: records an ingestion_run_errors row
        ),
    )
    assert cli.main(["sync-sources", "--scheduled"]) == 0
    # Run 2: one posting changes (rewrite + candidate refresh + re-evaluation), one disappears
    # (closure), so the UPDATE and DELETE paths run too.
    web.json(
        GREENHOUSE_URL,
        greenhouse_board(
            greenhouse_job(1001, content="&lt;p&gt;Applicants must be 21 or older.&lt;/p&gt;")
        ),
    )
    assert cli.main(["sync-sources", "--scheduled"]) == 0

    with Session(pg_engine) as owner:
        runs = owner.scalars(select(IngestionRun)).all()
        assert [r.status for r in runs] == [IngestionRunStatus.PARTIAL, IngestionRunStatus.SUCCESS]
        assert (runs[0].created_count, runs[0].invalid_count) == (2, 1)
        assert (runs[1].updated_count, runs[1].closed_count) == (1, 1)
        assert len(runs[0].errors) == 1
        assert len(owner.scalars(select(Opportunity)).all()) == 2
        assert len(owner.scalars(select(OpportunityEvaluation)).all()) >= 2


@pytest.mark.postgres
@pytest.mark.parametrize(
    "table", ["auth_users", "auth_sessions", "profile_sources", "profile_source_artifacts"]
)
def test_role_cannot_read_private_tables(sync_role: Engine, table: str) -> None:
    with sync_role.connect() as connection, pytest.raises(ProgrammingError, match="permission"):
        connection.execute(text(f"SELECT 1 FROM {table}"))


@pytest.mark.postgres
def test_role_cannot_read_applications_or_write_the_profile(sync_role: Engine) -> None:
    with sync_role.connect() as connection:
        with pytest.raises(ProgrammingError, match="permission denied for table applications"):
            connection.execute(text("SELECT 1 FROM applications"))
        connection.rollback()
        with pytest.raises(ProgrammingError, match="permission denied for table profiles"):
            connection.execute(text("UPDATE profiles SET location = 'x'"))
        connection.rollback()
        with pytest.raises(ProgrammingError, match="permission denied"):
            connection.execute(text("CREATE TABLE should_not_exist (id int)"))
