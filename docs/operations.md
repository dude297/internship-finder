# Operations

There are no hosted services, scheduled jobs, or monitoring. The app runs locally (Milestone 3). Each section is labeled planned or implemented.

## Owner Account and Sessions (implemented, local)

- Create the owner once: `python -m app.cli create-owner --username <name>` (password via `getpass`).
- Rotate the password: `python -m app.cli set-password --username <name>`. This revokes every session of that user.
- Sessions expire after `SESSION_TTL_HOURS` (default 24). Logout deletes the session row. Expired rows are removed the next time the user logs in; there's no background cleanup yet.
- Disable an account without deleting data: `UPDATE auth_users SET is_active = false WHERE username = '<name>'` (its sessions stop working immediately).
- Failed logins are throttled per client IP in memory (10 per 15 minutes). A restart clears the counter. This is a local safeguard only ([deployment.md](deployment.md#blockers-before-any-hosted-deployment)).
- Nothing logs passwords, session tokens, CSRF tokens, or request bodies. Unexpected errors are logged server-side with their stack trace; clients get a generic `500`.

## Local Database (implemented)

`compose.yaml` runs PostgreSQL 18 on `127.0.0.1:5432` with a named volume `pgdata`. That volume holds the owner's private data: back it up yourself if it matters (for example, `docker compose exec postgres pg_dump -U internship_finder internship_finder > backup.sql`, stored **outside** the repository). `docker compose down -v` deletes it.

## Source Sync (implemented, manual)

Sources sync only when the owner asks: **Sync now** / **Sync all** on the Sources page, `POST /api/sources/{id}/sync` / `POST /api/sources/sync`, or `python -m app.cli sync-source <id-or-key>` / `sync-sources`. All use the same pipeline ([ADR-008](decisions/ADR-008-opportunity-ingestion-and-deduplication.md)). There is **no scheduler**: the database is local, so a hosted runner can't reach it.

Measured locally on 2026-09-27 against the live discovery feed (disposable database, synthetic profile, Windows + Docker PostgreSQL 18): the first sync of 1,034 postings took about 22 s (including one evaluation per posting); a repeat answered `304` in under 0.5 s; a forced full re-process (validators cleared) found all 1,034 unchanged in under 1 s. A 50-item page of the opportunity list took 30–130 ms at ~1,100 opportunities.

## Run Summaries (implemented)

Every sync records an `ingestion_runs` row: status (`running`, `success`, `partial`, `failed`, `no_change`), start/finish time, the source's own snapshot time, and counts (fetched, normalized, created, updated, deduplicated, unchanged, closed, reactivated, invalid, errors). Up to 100 safe per-item errors are stored per run (stage, short code, message, source item ID). The Sources page shows each source's latest run; `GET /api/sources/{id}/runs` lists recent ones. Each finished run is also logged as one line with the source key and counts. No payloads, headers, or stack traces are stored or returned.

## Failed and Partial Runs (implemented)

- One failing source doesn't stop the others in "sync all".
- `failed` (network error, timeout, rate limit longer than 30 s, HTTP error, oversized or non-JSON response, unexpected format, incomplete snapshot): nothing is changed. The reason is on the run. Fix or wait, then sync again.
- `partial` (some items invalid or conflicting): valid items are imported, but nothing is closed, and the HTTP validators aren't stored, so the next sync fetches the full snapshot again. A recurring partial run (for example, a persistent identity conflict) means that source's missing postings won't close until it's resolved; the run's problems list names the items.
- Only one sync of a source can run at a time: a partial unique index allows one `running` run per source, so a concurrent second start gets "already syncing" (`409` from the API). Different sources can sync concurrently.
- A run left `running` (e.g. the process stopped mid-sync) is marked `failed` by the next sync of that source after 15 minutes; until then that source reports "already syncing".
- Retries: at most 3 attempts per request on timeouts, connection errors, 429, and 5xx, with short backoff. There's no alerting; check the Sources page.

## Closed Postings (implemented)

When a complete successful sync no longer lists a posting, its source record is marked closed (`is_active = false`, `closed_at`). Nothing is deleted: the opportunity, its evaluations, and its application tracking stay. An opportunity is shown as **closed** when all of its automated source records are closed; the default list view hides closed postings, and **Show → Closed postings / Everything** finds them. If the posting reappears, the record reopens. There's no age-based "stale" rule.

## Database Backup Considerations (planned)

Not configured yet. The selected provider is Neon Free ([ADR-004](decisions/ADR-004-technology-stack.md)); its free-tier history/restore window is limited, so the plan must include a free, self-run backup (e.g. a scheduled `pg_dump`). It must cover backup frequency, retention, and a tested restore procedure.

## Logs (planned)

Structured logs as described in [ENGINEERING_GUIDELINES.md §11](../ENGINEERING_GUIDELINES.md#11-logging-and-observability). No secrets, and no unnecessary sensitive profile data. The log destination is TBD.

## Evaluation History and Re-evaluation (implemented; not scheduled)

`app.repositories` appends `opportunity_evaluations` rows with their rule results. Earlier rows are kept as history, and the latest `evaluated_at` is current. Evaluations run:

- when an opportunity is created or updated by hand or by a sync (if a profile exists), **only if** its eligibility inputs changed since the latest evaluation (SHA-256 input fingerprint), so unchanged syncs and title-only edits add nothing
- for **every** opportunity when the profile is saved with a changed eligibility input (education timeline, date of birth, citizenships), in the same transaction as the profile update
- on demand, always: `POST /api/opportunities/{id}/evaluate`

Scaling note: profile re-evaluation is synchronous and proportional to the number of opportunities. With ~1,100 imported opportunities it took about 4 s locally (2026-09-27). Acceptable for a local single-user app; before hosted use or a much larger catalog, move it to batched or background re-evaluation (and consider evaluating only opportunities whose requirements read the changed fields). History still grows with every real input change; pruning is TBD.

Still not automatic: re-evaluation when the eligibility rules version changes, and when time passes an expected graduation or enrollment date (see Future Scheduled Jobs).

## Migrations

Schema changes are Alembic migrations (`backend/alembic/versions/`), validated in CI against a disposable PostgreSQL. No hosted database exists yet. Locally, run `alembic upgrade head` after pulling new migrations; it's applied to your own Compose database only.

## Environment Configuration

Backend: `DATABASE_URL` (required for everything except `/api/health`), `SESSION_TTL_HOURS`, `SESSION_COOKIE_SECURE`. See [`backend/.env.example`](../backend/.env.example), [development.md](development.md#environment-variables), and [deployment.md](deployment.md).

## Incident Handling (planned)

For a single-user tool, the minimum is to detect the failure (run summary or error log), record it in [PROJECT_STATE.md](../PROJECT_STATE.md) → Known Bugs, fix it with a regression test, and note it in [CHANGELOG.md](../CHANGELOG.md).

## Future Scheduled Jobs (planned)

- Recurring source sync (`python -m app.cli sync-sources`; the command exists, only the schedule is missing, and it needs a hosted database first)
- Source health checks (e.g. alert on repeated `failed`/`partial` runs)
- Re-evaluation when eligibility rules or scoring version change, or when the user's projected education status crosses a date (graduation, enrollment)
- In-app alerts/digests (no email/SMS services initially)

Scheduler: GitHub Actions scheduled workflows (selected, not configured), or later a self-hosted runner. No paid scheduler. Workflows only orchestrate Python commands. If free-tier limits (Actions minutes, Neon compute, Render hours) are reached, jobs defer or fail visibly rather than incur charges ([ADR-004](decisions/ADR-004-technology-stack.md)).

## Maintenance

Update this file whenever runtime or monitoring behavior changes.
