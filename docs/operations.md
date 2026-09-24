# Operations

**Nothing here is implemented.** There are no running services, jobs, or monitoring. Each section describes intended behavior and is labeled accordingly.

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

Not configured yet. It depends on the database provider (TBD). It must cover backup frequency, retention, and a tested restore procedure.

## Logs (planned)

Structured logs as described in [ENGINEERING_GUIDELINES.md §11](../ENGINEERING_GUIDELINES.md#11-logging-and-observability). No secrets, and no unnecessary sensitive profile data. The log destination is TBD.

## Environment Configuration

No environment variables are required yet. See [`.env.example`](../.env.example) and [deployment.md](deployment.md).

## Incident Handling (planned)

For a single-user tool, the minimum is to detect the failure (run summary or error log), record it in [PROJECT_STATE.md](../PROJECT_STATE.md) → Known Bugs, fix it with a regression test, and note it in [CHANGELOG.md](../CHANGELOG.md).

## Future Scheduled Jobs (planned)

- Recurring source discovery/refresh
- Stale opportunity cleanup
- Re-evaluation when eligibility rules or scoring version change
- Alerts/digests

The scheduler technology is TBD.

## Maintenance

Update this file whenever runtime or monitoring behavior changes.
