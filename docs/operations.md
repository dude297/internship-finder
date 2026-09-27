# Operations

There are no hosted services, jobs, or monitoring. The app runs locally (Milestone 2). Each section is labeled planned or implemented.

## Owner Account and Sessions (implemented, local)

- Create the owner once: `python -m app.cli create-owner --username <name>` (password via `getpass`).
- Rotate the password: `python -m app.cli set-password --username <name>`. This revokes every session of that user.
- Sessions expire after `SESSION_TTL_HOURS` (default 24). Logout deletes the session row. Expired rows are removed the next time the user logs in; there's no background cleanup yet.
- Disable an account without deleting data: `UPDATE auth_users SET is_active = false WHERE username = '<name>'` (its sessions stop working immediately).
- Failed logins are throttled per client IP in memory (10 per 15 minutes). A restart clears the counter. This is a local safeguard only ([deployment.md](deployment.md#blockers-before-any-hosted-deployment)).
- Nothing logs passwords, session tokens, CSRF tokens, or request bodies. Unexpected errors are logged server-side with their stack trace; clients get a generic `500`.

## Local Database (implemented)

`compose.yaml` runs PostgreSQL 18 on `127.0.0.1:5432` with a named volume `pgdata`. That volume holds the owner's private data: back it up yourself if it matters (for example, `docker compose exec postgres pg_dump -U internship_finder internship_finder > backup.sql`, stored **outside** the repository). `docker compose down -v` deletes it.

## Source Job Monitoring (planned)

Each ingestion run should produce a structured run summary per source, for example:

```text
150 fetched
143 normalized
4 duplicates
2 invalid
1 source error
```

It should also record the start/end time, status, and error categories. Where these summaries are stored and viewed is TBD.

## Failed Ingestion Runs (planned)

- One failing source must not stop other sources.
- Failures are logged with source, operation, and error category.
- Retry and alerting policy: TBD.

## Stale Opportunity Cleanup (planned)

Opportunities not seen for a period (TBD) should be marked stale/closed using `last_seen_at`, not deleted, so history and application state are kept.

## Database Backup Considerations (planned)

Not configured yet. The selected provider is Neon Free ([ADR-004](decisions/ADR-004-technology-stack.md)); its free-tier history/restore window is limited, so the plan must include a free, self-run backup (e.g. a scheduled `pg_dump`). It must cover backup frequency, retention, and a tested restore procedure.

## Logs (planned)

Structured logs as described in [ENGINEERING_GUIDELINES.md §11](../ENGINEERING_GUIDELINES.md#11-logging-and-observability). No secrets, and no unnecessary sensitive profile data. The log destination is TBD.

## Evaluation History and Re-evaluation (implemented; not scheduled)

`app.repositories.evaluate_and_save` appends a new `opportunity_evaluations` row with its rule results. Earlier rows are kept as history, and the latest `evaluated_at` is current. It runs automatically:

- when an opportunity is created or updated (if a profile exists)
- for **every** opportunity when the profile is saved with a changed eligibility input (education timeline, date of birth, citizenships), in the same transaction as the profile update
- on demand: `POST /api/opportunities/{id}/evaluate`

Scaling note: profile re-evaluation is synchronous and proportional to the number of opportunities. That's fine for a manual, single-user catalog (tens to hundreds). Once ingestion adds thousands, move it to batched or background re-evaluation (and consider evaluating only opportunities whose requirements read the changed fields). Each evaluation appends rows, so history grows with every edit; pruning is TBD.

Still not automatic: re-evaluation when the eligibility rules version changes, and when time passes an expected graduation or enrollment date (see Future Scheduled Jobs).

## Migrations

Schema changes are Alembic migrations (`backend/alembic/versions/`), validated in CI against a disposable PostgreSQL. No hosted database exists yet. Locally, run `alembic upgrade head` after pulling new migrations; it's applied to your own Compose database only.

## Environment Configuration

Backend: `DATABASE_URL` (required for everything except `/api/health`), `SESSION_TTL_HOURS`, `SESSION_COOKIE_SECURE`. See [`backend/.env.example`](../backend/.env.example), [development.md](development.md#environment-variables), and [deployment.md](deployment.md).

## Incident Handling (planned)

For a single-user tool, the minimum is to detect the failure (run summary or error log), record it in [PROJECT_STATE.md](../PROJECT_STATE.md) → Known Bugs, fix it with a regression test, and note it in [CHANGELOG.md](../CHANGELOG.md).

## Future Scheduled Jobs (planned)

- Recurring source discovery/refresh (ATS refreshes, deadline refreshes)
- Stale opportunity cleanup
- Source health checks
- Re-evaluation when eligibility rules or scoring version change, or when the user's projected education status crosses a date (graduation, enrollment)
- In-app alerts/digests (no email/SMS services initially)

Scheduler: GitHub Actions scheduled workflows (selected, not configured), or later a self-hosted runner. No paid scheduler. Workflows only orchestrate Python commands. If free-tier limits (Actions minutes, Neon compute, Render hours) are reached, jobs defer or fail visibly rather than incur charges ([ADR-004](decisions/ADR-004-technology-stack.md)).

## Maintenance

Update this file whenever runtime or monitoring behavior changes.
