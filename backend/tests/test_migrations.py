"""The Alembic migrations against real PostgreSQL: up, down, up again, and no model drift."""

import json
import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, Profile
from app.repositories import fit_profile_input
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
MILESTONE_5_TABLES = MILESTONE_2_TABLES | {
    "ingestion_sources",
    "ingestion_runs",
    "ingestion_run_errors",
    "opportunity_identifiers",
    "profile_source_artifacts",
}
TABLES = MILESTONE_5_TABLES | {"opportunity_requirement_candidates"}
MILESTONE_5_REVISION = "c5a1e0f3d7b2"
MILESTONE_6_REVISION = "e6d1a4b8c2f9"
MILESTONE_7_1_REVISION = "f2a7c9d4e1b3"
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

    command.downgrade(config, MILESTONE_5_REVISION)
    assert tables(pg_engine) == MILESTONE_5_TABLES

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
    assert sorted(tuple(row) for row in sources) == [
        ("community_feed", "zshah-tech-internships", None, True),
        ("curated_registry", "program-registry", None, True),  # Milestone 8 (ADR-014 §5)
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


MILESTONE_35_REVISION = "92a17353e5a8"
M4_COLUMNS = {
    "profiles": {
        "interests",
        "preferred_locations",
        "remote_preference",
        "availability_start",
        "availability_end",
    },
    "opportunity_evaluations": {
        "fit_score",
        "score_breakdown",
        "scoring_version",
        "fit_input_fingerprint",
    },
    "ingestion_sources": {"scope"},
    "ingestion_runs": {"filtered_count"},
}
M4_CHECKS = {
    "profiles": {"ck_profiles_remote_preference", "ck_profiles_availability_end_not_before_start"},
    "opportunity_evaluations": {
        "ck_opportunity_evaluations_fit_score_range",
        "ck_opportunity_evaluations_fit_input_fingerprint_length",
        "ck_opportunity_evaluations_fit_fields_together",
    },
    "ingestion_sources": {
        "ck_ingestion_sources_source_scope",
        "ck_ingestion_sources_builtin_scope_all",
    },
}


def columns(engine: Engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def checks(engine: Engine, table: str) -> set[str]:
    return {str(c["name"]) for c in inspect(engine).get_check_constraints(table)}


def test_milestone_4_migration_round_trip(pg_engine: Engine, pg_url: str) -> None:
    config = alembic_config(pg_url)
    for table, names in M4_COLUMNS.items():
        assert names <= columns(pg_engine, table)
    for table, names in M4_CHECKS.items():
        assert names <= checks(pg_engine, table)

    # A board added before Milestone 4 must keep importing everything after the upgrade.
    command.downgrade(config, MILESTONE_35_REVISION)
    for table, names in M4_COLUMNS.items():
        assert not names & columns(pg_engine, table)
    for table, names in M4_CHECKS.items():
        assert not names & checks(pg_engine, table)
    with pg_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ingestion_sources (id, kind, identifier, display_name)"
                " VALUES (gen_random_uuid(), 'greenhouse', 'examplelegacy', 'Example Legacy')"
            )
        )

    command.upgrade(config, "head")
    with pg_engine.begin() as connection:
        scopes = dict(
            connection.execute(text("SELECT identifier, scope FROM ingestion_sources")).all()
        )
        connection.execute(text("DELETE FROM ingestion_sources WHERE kind = 'greenhouse'"))
    assert scopes == {
        "zshah-tech-internships": "all",
        "examplelegacy": "all",
        "program-registry": "all",
    }


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE profiles SET availability_start = '2041-09-01', availability_end = '2041-06-01'",
        "UPDATE profiles SET remote_preference = 'sometimes'",
        "UPDATE ingestion_sources SET scope = 'internships_only'",  # the built-in feed
        "UPDATE ingestion_sources SET scope = 'some'",
        "UPDATE opportunity_evaluations SET fit_score = 101, scoring_version = 'v1',"
        " score_breakdown = '{}', fit_input_fingerprint = repeat('a', 64)",
        "UPDATE opportunity_evaluations SET fit_score = 50",  # without the other fit fields
        "UPDATE opportunity_evaluations SET fit_score = 50, scoring_version = 'v1',"
        " score_breakdown = '{}', fit_input_fingerprint = 'short'",
    ],
)
def test_milestone_4_constraints(pg_engine: Engine, statement: str) -> None:
    with pg_engine.connect() as connection, connection.begin() as transaction:
        connection.execute(
            text(
                "INSERT INTO profiles (id) VALUES ('00000000-0000-4000-8000-000000000001');"
                "INSERT INTO opportunities (id, title, organization, opportunity_type)"
                " VALUES ('00000000-0000-4000-8000-000000000002', 'Synthetic', 'Example',"
                " 'other');"
                "INSERT INTO opportunity_evaluations (id, profile_id, opportunity_id,"
                " eligibility_status, eligibility_rules_version, depends_on_projected_status)"
                " VALUES (gen_random_uuid(), '00000000-0000-4000-8000-000000000001',"
                " '00000000-0000-4000-8000-000000000002', 'eligible', 'v1', false)"
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(text(statement))
        transaction.rollback()


MILESTONE_4_REVISION = "b41e7c9d2f60"
PROFILE_ID = "00000000-0000-4000-8000-000000000005"
# (fact_key, extraction_method, verified_by_user) → expected review_state after the upgrade
LEGACY_FACTS = {
    ("manual_unverified", "manual", False): "accepted",
    ("manual_verified", "manual", True): "accepted",
    ("parsed_verified", "deterministic_parser", True): "accepted",
    ("parsed_unverified", "deterministic_parser", False): "pending",
    ("inferred_unverified", "ai_inference", False): "pending",
}


def test_milestone_5_migration_backfills_review_state(pg_engine: Engine, pg_url: str) -> None:
    config = alembic_config(pg_url)
    assert "review_state" in columns(pg_engine, "profile_facts")

    command.downgrade(config, MILESTONE_4_REVISION)
    assert "profile_source_artifacts" not in tables(pg_engine)
    assert "review_state" not in columns(pg_engine, "profile_facts")
    assert not {"content_type", "byte_size", "parser_name", "parser_version"} & columns(
        pg_engine, "profile_sources"
    )
    with pg_engine.begin() as connection:
        connection.execute(text(f"INSERT INTO profiles (id) VALUES ('{PROFILE_ID}')"))
        for key, method, verified in LEGACY_FACTS:
            connection.execute(
                text(
                    "INSERT INTO profile_facts (id, profile_id, category, fact_key, value,"
                    " source_kind, extraction_method, extractor_name, verified_by_user)"
                    " VALUES (gen_random_uuid(), :profile, 'skill', :key, '{\"name\": \"S\"}',"
                    " 'resume', :method, 'synthetic', :verified)"
                ),
                {"profile": PROFILE_ID, "key": key, "method": method, "verified": verified},
            )

    command.upgrade(config, "head")
    with pg_engine.begin() as connection:
        states = dict(
            connection.execute(text("SELECT fact_key, review_state FROM profile_facts")).all()
        )
        connection.execute(text(f"DELETE FROM profiles WHERE id = '{PROFILE_ID}'"))
    # Exactly the facts the Milestone 4 fit filter used are accepted: no fit input changes.
    assert states == {key: state for (key, _, _), state in LEGACY_FACTS.items()}


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE profile_facts SET review_state = 'maybe'",
        "UPDATE profile_facts SET review_state = NULL",
        # A non-manual fact is accepted exactly when the owner verified it.
        "UPDATE profile_facts SET review_state = 'accepted', verified_by_user = false",
        "UPDATE profile_facts SET review_state = 'pending', verified_by_user = true",
        "UPDATE profile_sources SET byte_size = 0",
        "INSERT INTO profile_sources (id, profile_id, kind, content_sha256)"
        " SELECT gen_random_uuid(), profile_id, kind, content_sha256 FROM profile_sources",
        "INSERT INTO profile_source_artifacts (profile_source_id, content)"
        " VALUES (gen_random_uuid(), 'x')",
    ],
)
def test_milestone_5_constraints(pg_engine: Engine, statement: str) -> None:
    with pg_engine.connect() as connection, connection.begin() as transaction:
        connection.execute(
            text(
                f"INSERT INTO profiles (id) VALUES ('{PROFILE_ID}');"
                "INSERT INTO profile_sources (id, profile_id, kind, content_sha256, byte_size)"
                f" VALUES ('00000000-0000-4000-8000-000000000006', '{PROFILE_ID}', 'resume',"
                " repeat('a', 64), 10);"
                "INSERT INTO profile_facts (id, profile_id, profile_source_id, category, fact_key,"
                " value, source_kind, extraction_method, verified_by_user, review_state)"
                f" VALUES (gen_random_uuid(), '{PROFILE_ID}',"
                " '00000000-0000-4000-8000-000000000006', 'skill', 'resume.000',"
                " '{\"name\": \"S\"}', 'resume', 'deterministic_parser',"
                " false, 'pending')"
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(text(statement))
        transaction.rollback()


def test_deleting_a_source_removes_its_artifact_and_facts_only(pg_engine: Engine) -> None:
    source = "00000000-0000-4000-8000-000000000007"
    with pg_engine.connect() as connection, connection.begin() as transaction:
        connection.execute(
            text(
                f"INSERT INTO profiles (id) VALUES ('{PROFILE_ID}');"
                "INSERT INTO profile_sources (id, profile_id, kind)"
                f" VALUES ('{source}', '{PROFILE_ID}', 'resume');"
                f"INSERT INTO profile_source_artifacts VALUES ('{source}', 'synthetic bytes');"
                "INSERT INTO profile_facts (id, profile_id, profile_source_id, category, fact_key,"
                " value, source_kind, extraction_method, verified_by_user, review_state) VALUES"
                f" (gen_random_uuid(), '{PROFILE_ID}', '{source}', 'skill', 'resume.000',"
                " '{\"name\": \"S\"}', 'resume', 'deterministic_parser', true, 'accepted'),"
                f" (gen_random_uuid(), '{PROFILE_ID}', NULL, 'skill', 'match_profile.000',"
                " '{\"name\": \"S\"}', 'manual', 'manual', true, 'accepted');"
                f"DELETE FROM profile_sources WHERE id = '{source}'"
            )
        )
        remaining = connection.execute(
            text("SELECT fact_key FROM profile_facts WHERE profile_id = :p"), {"p": PROFILE_ID}
        ).scalars()
        artifacts = connection.scalar(text("SELECT count(*) FROM profile_source_artifacts"))
        assert list(remaining) == ["match_profile.000"]
        assert artifacts == 0
        transaction.rollback()


# --- review_state server default (deployment compatibility with Milestone 4) -------------------
# The migration gives review_state a server default of 'accepted' so the *previous* (Milestone 4)
# application, whose manual Match Profile inserts never name review_state, can still save after
# this migration runs (and so a Render rollback to Milestone 4 doesn't break). Milestone 5 code
# must still state review_state on every write; these tests are about the deployment gap, not an
# invitation to omit it going forward.


def test_milestone_5_m4_manual_match_profile_facts_backfill_to_accepted(
    pg_engine: Engine, pg_url: str
) -> None:
    """The exact shape Milestone 4's `save_match_profile` writes (no review_state column at all):
    manual, verified, `match_profile.NNN` keys, skill/project categories. Both become `accepted`,
    matching the Milestone 4 fit filter (manual facts are always used)."""
    config = alembic_config(pg_url)
    command.downgrade(config, MILESTONE_4_REVISION)
    with pg_engine.begin() as connection:
        connection.execute(text(f"INSERT INTO profiles (id) VALUES ('{PROFILE_ID}')"))
        connection.execute(
            text(
                "INSERT INTO profile_facts (id, profile_id, category, fact_key, value,"
                " source_kind, extraction_method, verified_by_user) VALUES"
                f" (gen_random_uuid(), '{PROFILE_ID}', 'skill', 'match_profile.000',"
                " '{\"name\": \"Python\"}', 'manual', 'manual', true),"
                f" (gen_random_uuid(), '{PROFILE_ID}', 'project', 'match_profile.001',"
                " '{\"name\": \"App\", \"description\": null}', 'manual', 'manual', true)"
            )
        )

    command.upgrade(config, "head")
    with pg_engine.begin() as connection:
        states = (
            connection.execute(
                text(
                    "SELECT review_state FROM profile_facts WHERE profile_id = :p ORDER BY fact_key"
                ),
                {"p": PROFILE_ID},
            )
            .scalars()
            .all()
        )
        connection.execute(text(f"DELETE FROM profiles WHERE id = '{PROFILE_ID}'"))
    assert states == ["accepted", "accepted"]


def test_head_accepts_m4_manual_insert_without_review_state(pg_engine: Engine) -> None:
    """At head, an M4-style manual insert that omits review_state succeeds (the server default
    fills it) and gets 'accepted'."""
    with pg_engine.connect() as connection, connection.begin() as transaction:
        connection.execute(
            text(
                f"INSERT INTO profiles (id) VALUES ('{PROFILE_ID}');"
                "INSERT INTO profile_facts (id, profile_id, category, fact_key, value,"
                " source_kind, extraction_method, verified_by_user) VALUES"
                f" (gen_random_uuid(), '{PROFILE_ID}', 'skill', 'match_profile.000',"
                " '{\"name\": \"Python\"}', 'manual', 'manual', true)"
            )
        )
        state = connection.scalar(
            text("SELECT review_state FROM profile_facts WHERE fact_key = 'match_profile.000'")
        )
        transaction.rollback()
    assert state == "accepted"


def test_head_rejects_unverified_parser_insert_without_review_state(pg_engine: Engine) -> None:
    """An unverified non-manual insert that omits review_state would default to 'accepted', which
    the CHECK rejects: review_state must be 'accepted' exactly when verified_by_user."""
    with pg_engine.connect() as connection, connection.begin() as transaction:
        connection.execute(text(f"INSERT INTO profiles (id) VALUES ('{PROFILE_ID}')"))
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO profile_facts (id, profile_id, category, fact_key, value,"
                    " source_kind, extraction_method, verified_by_user) VALUES"
                    f" (gen_random_uuid(), '{PROFILE_ID}', 'skill', 'resume.000',"
                    " '{\"name\": \"Python\"}', 'resume', 'deterministic_parser', false)"
                )
            )
        transaction.rollback()


def test_head_accepts_verified_parser_insert_without_review_state(pg_engine: Engine) -> None:
    """A verified non-manual insert that omits review_state also defaults to 'accepted', and the
    CHECK allows it: verified means the owner already accepted the fact, so 'accepted' is the
    only value consistent with `verified_by_user = true`."""
    with pg_engine.connect() as connection, connection.begin() as transaction:
        connection.execute(text(f"INSERT INTO profiles (id) VALUES ('{PROFILE_ID}')"))
        connection.execute(
            text(
                "INSERT INTO profile_facts (id, profile_id, category, fact_key, value,"
                " source_kind, extraction_method, verified_by_user) VALUES"
                f" (gen_random_uuid(), '{PROFILE_ID}', 'skill', 'resume.001',"
                " '{\"name\": \"Python\"}', 'resume', 'deterministic_parser', true)"
            )
        )
        state = connection.scalar(
            text("SELECT review_state FROM profile_facts WHERE fact_key = 'resume.001'")
        )
        transaction.rollback()
    assert state == "accepted"


def test_head_explicit_pending_parser_insert_succeeds(pg_engine: Engine) -> None:
    with pg_engine.connect() as connection, connection.begin() as transaction:
        connection.execute(
            text(
                f"INSERT INTO profiles (id) VALUES ('{PROFILE_ID}');"
                "INSERT INTO profile_facts (id, profile_id, category, fact_key, value,"
                " source_kind, extraction_method, verified_by_user, review_state) VALUES"
                f" (gen_random_uuid(), '{PROFILE_ID}', 'skill', 'resume.002',"
                " '{\"name\": \"Python\"}', 'resume', 'deterministic_parser', false, 'pending')"
            )
        )
        transaction.rollback()


def test_head_rejects_explicit_accepted_unverified_parser_insert(pg_engine: Engine) -> None:
    with pg_engine.connect() as connection, connection.begin() as transaction:
        connection.execute(text(f"INSERT INTO profiles (id) VALUES ('{PROFILE_ID}')"))
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO profile_facts (id, profile_id, category, fact_key, value,"
                    " source_kind, extraction_method, verified_by_user, review_state) VALUES"
                    f" (gen_random_uuid(), '{PROFILE_ID}', 'skill', 'resume.003',"
                    " '{\"name\": \"Python\"}', 'resume', 'deterministic_parser', false,"
                    " 'accepted')"
                )
            )
        transaction.rollback()


# (fact_key, category, extraction_method, verified_by_user, value) - a synthetic mix like
# production's Match Profile plus imported facts, across every category fit v1 reads.
FIT_TEST_FACTS: list[tuple[str, str, str, bool, dict[str, object]]] = [
    ("a1", "skill", "manual", True, {"name": "Python"}),
    ("a2", "skill", "manual", False, {"name": "SQL"}),
    ("a3", "skill", "deterministic_parser", True, {"name": "Rust"}),
    ("a4", "skill", "deterministic_parser", False, {"name": "Go"}),
    ("b1", "course", "manual", True, {"name": "Algorithms"}),
    ("b2", "course", "deterministic_parser", False, {"name": "Databases"}),
    ("c1", "project", "manual", True, {"name": "Tracker", "description": "A tracker"}),
    ("c2", "project", "deterministic_parser", True, {"name": "Bot", "description": None}),
    ("d1", "research", "manual", True, {"name": "Vision", "description": None}),
    ("d2", "research", "deterministic_parser", False, {"name": "NLP", "description": "text"}),
]


def test_m4_fit_filter_survives_the_migration(pg_engine: Engine, pg_url: str) -> None:
    """`fit_profile_input` after the migration selects exactly what the Milestone 4 fit filter
    (`verified_by_user OR extraction_method = 'manual'`) selected before it: fit input is
    unchanged by the migration, for a realistic mix of manual and imported facts."""
    config = alembic_config(pg_url)
    command.downgrade(config, MILESTONE_4_REVISION)
    try:
        with pg_engine.begin() as connection:
            connection.execute(text(f"INSERT INTO profiles (id) VALUES ('{PROFILE_ID}')"))
            for key, category, method, verified, value in FIT_TEST_FACTS:
                value_json = json.dumps(value).replace("'", "''")
                connection.execute(
                    text(
                        "INSERT INTO profile_facts (id, profile_id, category, fact_key, value,"
                        " source_kind, extraction_method, verified_by_user) VALUES"
                        f" (gen_random_uuid(), '{PROFILE_ID}', '{category}', '{key}',"
                        f" '{value_json}', 'manual', '{method}', {str(verified).lower()})"
                    )
                )
            # What the Milestone 4 fit filter selected, in the app's own order.
            m4_selection = connection.execute(
                text(
                    "SELECT category, value FROM profile_facts WHERE profile_id = :p"
                    " AND (verified_by_user OR extraction_method = 'manual')"
                    " ORDER BY created_at, fact_key, id"
                ),
                {"p": PROFILE_ID},
            ).all()
    finally:
        # However the insert/select above goes, leave the shared engine at head: every other
        # test in this session assumes it.
        command.upgrade(config, "head")

    with pg_engine.connect() as connection:
        session = Session(bind=connection)
        profile = session.get(Profile, uuid.UUID(PROFILE_ID))
        assert profile is not None
        result = fit_profile_input(session, profile)
        session.close()
    with pg_engine.begin() as connection:
        connection.execute(text(f"DELETE FROM profiles WHERE id = '{PROFILE_ID}'"))

    expected_skills = tuple(v["name"] for c, v in m4_selection if c == "skill")
    expected_courses = tuple(v["name"] for c, v in m4_selection if c == "course")
    expected_projects = [v["name"] for c, v in m4_selection if c == "project"]
    expected_research = [v["name"] for c, v in m4_selection if c == "research"]

    assert result.skills == expected_skills
    assert result.courses == expected_courses
    assert [p.name for p in result.projects] == expected_projects
    assert [r.name for r in result.research] == expected_research
    # Sanity: the fixture actually exercises exclusion (unverified, non-manual facts left out).
    assert expected_skills == ("Python", "SQL", "Rust")
    assert expected_courses == ("Algorithms",)
    assert expected_projects == ["Tracker", "Bot"]
    assert expected_research == ["Vision"]


# --- Milestone 6: requirement candidates, staleness, and Ashby (ADR-012) -----------------------

CANDIDATES_TABLE = "opportunity_requirement_candidates"
OPPORTUNITY_ID = "00000000-0000-4000-8000-000000000008"
ASHBY_SOURCE_ID = "00000000-0000-4000-8000-000000000009"


def test_milestone_6_migration_round_trip(pg_engine: Engine, pg_url: str) -> None:
    config = alembic_config(pg_url)
    assert CANDIDATES_TABLE in tables(pg_engine)
    assert {"requirements_stale_since", "requirement_extraction_fingerprint"} <= columns(
        pg_engine, "opportunities"
    )

    with pg_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO opportunities (id, title, organization, opportunity_type)"
                f" VALUES ('{OPPORTUNITY_ID}', 'Synthetic Robotics Intern', 'Example Robotics',"
                " 'internship')"
            )
        )

    # 'ashby' is rejected before the upgrade.
    command.downgrade(config, MILESTONE_5_REVISION)
    assert CANDIDATES_TABLE not in tables(pg_engine)
    assert not {"requirements_stale_since", "requirement_extraction_fingerprint"} & columns(
        pg_engine, "opportunities"
    )
    with pg_engine.connect() as connection, connection.begin() as transaction:
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO ingestion_sources (id, kind, identifier, display_name, scope)"
                    f" VALUES ('{ASHBY_SOURCE_ID}', 'ashby', 'exampleboard', 'Example Board',"
                    " 'internships_only')"
                )
            )
        transaction.rollback()

    try:
        # Upgrading preserves the pre-existing opportunity row and now accepts 'ashby'.
        command.upgrade(config, MILESTONE_6_REVISION)
        assert CANDIDATES_TABLE in tables(pg_engine)
        with pg_engine.begin() as connection:
            title = connection.scalar(
                text("SELECT title FROM opportunities WHERE id = :id"), {"id": OPPORTUNITY_ID}
            )
            assert title == "Synthetic Robotics Intern"
            connection.execute(
                text(
                    "INSERT INTO ingestion_sources (id, kind, identifier, display_name, scope)"
                    f" VALUES ('{ASHBY_SOURCE_ID}', 'ashby', 'exampleboard', 'Example Board',"
                    " 'internships_only')"
                )
            )

        # The downgrade refuses while the Ashby source exists...
        with pytest.raises(RuntimeError, match="Ashby source"):
            command.downgrade(config, MILESTONE_5_REVISION)
        assert CANDIDATES_TABLE in tables(pg_engine)

        # ...and succeeds once it's gone, still preserving the opportunity row.
        with pg_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM ingestion_sources WHERE id = :id"), {"id": ASHBY_SOURCE_ID}
            )
        command.downgrade(config, MILESTONE_5_REVISION)
        assert CANDIDATES_TABLE not in tables(pg_engine)
        with pg_engine.begin() as connection:
            title = connection.scalar(
                text("SELECT title FROM opportunities WHERE id = :id"), {"id": OPPORTUNITY_ID}
            )
            assert title == "Synthetic Robotics Intern"
    finally:
        command.upgrade(config, "head")
        with pg_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM opportunities WHERE id = :id"), {"id": OPPORTUNITY_ID}
            )
            connection.execute(
                text("DELETE FROM ingestion_sources WHERE id = :id"), {"id": ASHBY_SOURCE_ID}
            )


VOLUNTEER_ID = "00000000-0000-4000-8000-000000000010"
OTHER_ID = "00000000-0000-4000-8000-000000000011"


def _insert_opportunity(connection: Connection, opportunity_id: str, kind: str) -> None:
    connection.execute(
        text(
            "INSERT INTO opportunities (id, title, organization, opportunity_type)"
            " VALUES (:id, 'Synthetic STEM Tutor Volunteer', 'Example Org', :kind)"
        ),
        {"id": opportunity_id, "kind": kind},
    )


def test_milestone_7_1_volunteer_type_round_trip(pg_engine: Engine, pg_url: str) -> None:
    config = alembic_config(pg_url)
    try:
        # Before the upgrade 'volunteer' is rejected; an existing 'other' row is kept as-is.
        command.downgrade(config, MILESTONE_6_REVISION)
        with pg_engine.begin() as connection:
            _insert_opportunity(connection, OTHER_ID, "other")
        with pg_engine.connect() as connection, connection.begin() as transaction:
            with pytest.raises(IntegrityError):
                _insert_opportunity(connection, VOLUNTEER_ID, "volunteer")
            transaction.rollback()

        command.upgrade(config, MILESTONE_7_1_REVISION)
        with pg_engine.begin() as connection:
            _insert_opportunity(connection, VOLUNTEER_ID, "volunteer")
            other_type = connection.scalar(
                text("SELECT opportunity_type FROM opportunities WHERE id = :id"), {"id": OTHER_ID}
            )
            assert other_type == "other"  # no backfill

        # The downgrade refuses while a volunteer opportunity exists...
        with pytest.raises(RuntimeError, match="volunteer"):
            command.downgrade(config, MILESTONE_6_REVISION)
        with pg_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM opportunities WHERE id = :id"), {"id": VOLUNTEER_ID}
            )
        # ...and succeeds once it's gone.
        command.downgrade(config, MILESTONE_6_REVISION)
    finally:
        command.upgrade(config, "head")
        with pg_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM opportunities WHERE id IN (:a, :b)"),
                {"a": VOLUNTEER_ID, "b": OTHER_ID},
            )
