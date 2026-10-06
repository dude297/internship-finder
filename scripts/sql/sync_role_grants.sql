-- Least-privilege database role for the scheduled production sync (ADR-027, Proposed).
--
-- Run as the schema OWNER role (the one Alembic uses), never as if_sync, against the target
-- database. Idempotent: safe to re-run after every migration that adds a table (the test
-- backend/tests/test_sync_role.py fails until the new table is listed below or excluded).
--
--   psql "$OWNER_URL" -v ON_ERROR_STOP=1 -f scripts/sql/sync_role_grants.sql
--
-- No password in this file. Set it separately, interactively, so it never reaches argv, shell
-- history, or a file:   psql "$OWNER_URL" -c '\password if_sync'
-- (docs/operations.md "Least-privilege sync role"). Neon requires >= 60 bits of entropy.
--
-- Creating the role in SQL matters on Neon: roles created in the console, CLI or API are made
-- members of neon_superuser (read/write ALL data, BYPASSRLS, CREATEROLE), which is the opposite
-- of least privilege. A role created with CREATE ROLE gets only PUBLIC's default privileges.
--
-- Stance: revoke everything, then grant table by table. Every table in the schema must appear
-- below exactly once, either as a GRANT or as an "excluded" line (the test parses both).
-- Grants are only what `python -m app.cli sync-sources --scheduled` exercises, traced through
-- app/ingestion/pipeline.py, app/repositories.py and app/services/requirement_candidates.py.
-- Foreign-key checks run as the table owner, so no REFERENCES privilege is needed; sequences:
-- none exist (every primary key is a client-generated UUID).

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'if_sync') THEN
        CREATE ROLE if_sync LOGIN;
    END IF;
END
$$;

-- Re-assert the attributes every run (a console edit can't silently widen them).
ALTER ROLE if_sync WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    NOINHERIT CONNECTION LIMIT 5;

DO $$
BEGIN
    -- Neon only: a console/CLI-created if_sync would be a neon_superuser member.
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'neon_superuser')
       AND pg_has_role('if_sync', 'neon_superuser', 'MEMBER') THEN
        REVOKE neon_superuser FROM if_sync;
    END IF;
END
$$;

-- Revoke by default, then grant explicitly.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM if_sync;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM if_sync;
REVOKE CREATE ON SCHEMA public FROM if_sync;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM if_sync;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM if_sync;

-- Schema check: the scheduled run compares alembic_version with the code's head first.
GRANT SELECT ON TABLE alembic_version TO if_sync;

-- Sources and run bookkeeping (_start_run, _finish, _fail, validators, last_success_at).
GRANT SELECT, UPDATE ON TABLE ingestion_sources TO if_sync;
GRANT SELECT, INSERT, UPDATE ON TABLE ingestion_runs TO if_sync;
-- SELECT too: the ORM loads the run's error collection.
GRANT SELECT, INSERT ON TABLE ingestion_run_errors TO if_sync;

-- The catalog. UPDATE on opportunities also covers SELECT ... FOR UPDATE row locks.
GRANT SELECT, INSERT, UPDATE ON TABLE opportunities TO if_sync;
GRANT SELECT, INSERT, UPDATE ON TABLE opportunity_source_records TO if_sync;
GRANT SELECT, INSERT ON TABLE opportunity_identifiers TO if_sync;
-- Read for eligibility. Sync never writes requirements (owner review does).
GRANT SELECT ON TABLE opportunity_requirements TO if_sync;
-- Extractor suggestions: created, refreshed, and pending ones deleted when no longer proposed.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE opportunity_requirement_candidates TO if_sync;

-- Re-evaluation of new/changed postings against the profile (append-only history).
GRANT SELECT, INSERT ON TABLE opportunity_evaluations TO if_sync;
GRANT INSERT ON TABLE eligibility_rule_results TO if_sync;
-- Read-only: the profile's preference/education columns and its facts feed eligibility and fit
-- (the ORM loads whole rows, so table-level; includes date_of_birth and citizenships).
GRANT SELECT ON TABLE profiles TO if_sync;
GRANT SELECT ON TABLE profile_facts TO if_sync;

-- Never needed by the sync: no grant, enforced by the test.
-- excluded: auth_users: owner credential hash
-- excluded: auth_sessions: live session token hashes
-- excluded: profile_sources: private resume/transcript metadata
-- excluded: profile_source_artifacts: private uploaded document contents
-- excluded: applications: owner's private application notes
-- excluded: application_events: private application history; the sync never touches applications
