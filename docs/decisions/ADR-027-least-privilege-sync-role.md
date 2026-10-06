# ADR-027: Least-Privilege Database Role for the Scheduled Sync

Status: Proposed (branch `chore/m17-least-privilege-sync-role`; subject to owner review). Code and runbook only: **not activated**, nothing was run against Neon.

Date: 2026-10-06

## Context

The scheduled sync ([ADR-009 amendment of 2026-10-01](ADR-009-hosted-deployment-architecture.md#amendment-2026-10-01-scheduled-source-sync-milestone-6)) connects to Neon with `PRODUCTION_DATABASE_URL`, the same owner role the app and Alembic use. Anyone who gets that secret out of a compromised workflow, action, or dependency can read the password hash and live session hashes, the private profile, resume artifacts, and application notes, and can drop tables. The security review of 2026-10-06 recorded this as debt and named a least-privilege ingestion role as the fix.

The sync needs far less than that. Constraints: $0 and no payment method ([ADR-004](ADR-004-technology-stack.md)); a public repository, so nothing secret in a file; Alembic stays the only way schemas change.

## Neon facts (accessed 2026-10-06)

- Roles created in the **console, CLI or API** are made members of `neon_superuser` ([Manage roles](https://neon.com/docs/manage/roles)): `CREATEDB`, `CREATEROLE`, `BYPASSRLS`, and membership in `pg_read_all_data` and `pg_write_all_data`, that is, read and write on every table. A role made that way is **not** least-privilege.
- Roles created with SQL `CREATE ROLE` "are only granted the basic public schema privileges ... must be selectively granted permissions for each database object" ([same page](https://neon.com/docs/manage/roles); [Database access](https://neon.com/docs/manage/database-access) recommends creating per-use roles in SQL). On PostgreSQL 15+ PUBLIC has only `USAGE` on `public`.
- Passwords need at least 60 bits of entropy. The CLI (`neon roles create --name x [--no-login]`) can create a role but there is no CLI command to reset a password; the console or API can ([Manage roles](https://neon.com/docs/manage/roles)). In SQL, `\password` in `psql` sets one without it appearing in argv or history.
- Limit: 500 roles per branch. The Free plan page ([Plans](https://neon.com/docs/introduction/plans)) lists no role or database limit and no charge for roles. Child branches duplicate the parent's roles.
- Pooling ([Connection pooling](https://neon.com/docs/connect/connection-pooling)): PgBouncer in transaction mode keeps a separate pool per user and database, so a new role gets its own pool; `-pooler` in the host is the only change. `SET`/`RESET`, `LISTEN`/`NOTIFY`, SQL `PREPARE` and session advisory locks are unsupported; protocol-level prepared statements work. The sync already runs through the pooled URL and uses none of the unsupported features, so the new role changes nothing here.
- Not documented, so not claimed: whether console role listing shows SQL-created roles (they do exist in `pg_roles`).

## Decision

1. **Role `if_sync`, created by SQL** with `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT 5`, by [`scripts/sql/sync_role_grants.sql`](../../scripts/sql/sync_role_grants.sql), run by the owner role. The file has no password. The owner sets it interactively (`\password if_sync`). The script re-asserts the attributes and removes any `neon_superuser` membership on every run, so a role created in the console by mistake is repaired.
2. **Revoke by default, grant table by table.** The script revokes everything on all tables and sequences in `public` and resets default privileges for the role, then grants only what `sync-sources --scheduled` exercises (matrix below). Grants were derived by tracing the code and **minimized by mutation**: the integration test was re-run with each grant removed to confirm the sync fails without it (and passes without the removed `SELECT` on `eligibility_rule_results`).
3. **Alembic stays with the owner.** `if_sync` owns nothing, can't create objects, and never runs migrations. Foreign-key checks run as the table owner, so no `REFERENCES` is needed. There are no sequences (UUID keys).
4. **No silent drift.** `backend/tests/test_sync_role.py` fails when a table (from the models or from the migrated database) is neither granted nor listed as `-- excluded:` in the SQL file, or is in both, so a new migration forces a grant review: grant the minimum, or exclude it with a reason. After merging a migration that adds a table, the owner re-runs the script (it is idempotent) as part of the release.
5. **A separate secret, with fallback.** The workflow uses `SYNC_DATABASE_URL` when set, else `PRODUCTION_DATABASE_URL`, so the change is inert until the owner sets it and rollback is deleting the secret. `PRODUCTION_DATABASE_URL` is **not** replaced: `backup-production.yml` ([ADR-021](ADR-021-encrypted-backups.md)) needs `pg_dump` access to everything and keeps it.

### Table and grant matrix

| Table | Grant | Why the sync needs it |
| --- | --- | --- |
| `alembic_version` | SELECT | the scheduled run checks the schema is at head |
| `ingestion_sources` | SELECT, UPDATE | list enabled sources; validators and `last_*` timestamps |
| `ingestion_runs` | SELECT, INSERT, UPDATE | start (running-run guard), counters, finish |
| `ingestion_run_errors` | SELECT, INSERT | per-item errors (the ORM loads the run's collection) |
| `opportunities` | SELECT, INSERT, UPDATE | create, canonical rewrite, `last_seen_at`; UPDATE covers `FOR UPDATE` locks |
| `opportunity_source_records` | SELECT, INSERT, UPDATE | per-source records, raw payload, closure |
| `opportunity_identifiers` | SELECT, INSERT | dedup identifiers |
| `opportunity_requirements` | SELECT | read for eligibility (sync never writes requirements) |
| `opportunity_requirement_candidates` | SELECT, INSERT, UPDATE, DELETE | extractor refresh; stale pending suggestions are deleted |
| `opportunity_evaluations` | SELECT, INSERT | latest fingerprint; append a new evaluation |
| `eligibility_rule_results` | INSERT | the evaluation's rule rows |
| `profiles` | SELECT | eligibility and fit inputs |
| `profile_facts` | SELECT | accepted skills, courses, projects, research for fit |
| `auth_users`, `auth_sessions` | none | credentials and sessions |
| `profile_sources`, `profile_source_artifacts` | none | private resume/transcript metadata and content |
| `applications` | none | private application notes |

## Alternatives considered

- **A role created with `neon roles create` / the console.** Rejected: automatic `neon_superuser` membership grants read and write on all data and `BYPASSRLS`.
- **Column-level `SELECT` on `profiles` and `profile_facts`.** Not done: the ORM selects whole rows. It would need `load_only` queries in `repositories.py`. The sync therefore can read the date of birth, citizenships and accepted facts, but cannot change them.
- **Replacing `PRODUCTION_DATABASE_URL`.** Rejected: it would break the weekly backup. A read-only backup role is a separate follow-up.
- **Row-level security or schema-per-concern.** More moving parts than one role with table grants.
- **`ALTER DEFAULT PRIVILEGES ... GRANT` to `if_sync` for future tables.** Rejected on purpose: a new table must be reviewed, not auto-granted.

## Consequences

- A compromised sync job can no longer read credentials, sessions, resume artifacts or notes, drop or alter tables, or write the profile. It can still read the profile and facts, and add, change and close catalog rows (the sync's own job); that is the residual risk.
- A migration that adds a table needs a one-line grant or exclusion, and a re-run of the script on production. If the owner forgets, the sync fails visibly (a red run), not silently.
- Code that starts using another table in the sync path (for example profile sources) fails the integration test's run as `if_sync` before it ships, which forces an explicit decision about widening the grant.
- Credential rotation: reset the role's password (SQL `\password`, console or API) and re-set `SYNC_DATABASE_URL`.
- Activation is an owner action: [operations.md](../operations.md#least-privilege-sync-role-owner-action-not-activated).
