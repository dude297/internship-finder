# Operations

There are no running services, jobs, or monitoring. Each section is labeled planned or implemented.

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

## Evaluation History and Re-evaluation (implemented as a library call; not scheduled)

`app.repositories.evaluate_and_save` appends a new `opportunity_evaluations` row with its rule results. Earlier rows are kept as history, and the latest `evaluated_at` is current. Nothing triggers re-evaluation automatically yet. Re-evaluation is needed when the eligibility rules version changes, when the canonical profile changes, and when the reference date moves past an expected graduation or enrollment date (see Future Scheduled Jobs). History pruning is TBD.

## Migrations

Schema changes are Alembic migrations (`backend/alembic/versions/`), validated in CI against a disposable PostgreSQL. No hosted database exists yet, so no migration has been applied anywhere persistent.

## Environment Configuration

No environment variables are required yet. See [`.env.example`](../.env.example) and [deployment.md](deployment.md).

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
