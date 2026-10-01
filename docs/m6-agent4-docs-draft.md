Draft text for Opus to merge into `docs/operations.md` and `docs/sources.md`, then delete this
file. Not meant to be read as a standalone doc.

## For docs/operations.md — replace the "Source Sync (implemented, manual)" section with:

## Source Sync (implemented, manual + scheduled)

Sources sync when the owner asks: **Sync now** / **Sync all** on the Sources page, `POST
/api/sources/{id}/sync` / `POST /api/sources/sync`, or `python -m app.cli sync-source
<id-or-key>` / `sync-sources`. All use the same pipeline
([ADR-008](decisions/ADR-008-opportunity-ingestion-and-deduplication.md)).

Production also syncs on a fixed schedule: a GitHub Actions workflow
(`.github/workflows/sync-production.yml`) runs `python -m app.cli sync-sources --scheduled`
against Neon at 06:17 and 18:17 America/Los_Angeles, and on manual dispatch from the Actions tab
(useful to run one on demand, or to recover after the 60-day public-repo inactivity auto-disable —
see [the ADR-009 amendment](decisions/ADR-009-hosted-deployment-architecture.md#amendment-2026-10-01-scheduled-source-sync-milestone-6)).
It connects to Neon directly with an environment-scoped secret, not through Render, so it adds no
new path to the FastAPI service and doesn't keep Render awake. Local development has no
scheduler: the database is local, so a hosted runner can't reach it.

Measured locally on 2026-09-27 against the live discovery feed (disposable database, synthetic
profile, Windows + Docker PostgreSQL 18): the first sync of 1,034 postings took about 22 s
(including one evaluation per posting); a repeat answered `304` in under 0.5 s; a forced full
re-process (validators cleared) found all 1,034 unchanged in under 1 s. A 50-item page of the
opportunity list took 30–130 ms at ~1,100 opportunities.

### Scheduled sync exit codes (CLI)

`python -m app.cli sync-sources` (and `sync-source`) exit `0` when every source it attempted
finished `success`, `no_change`, or `partial`; `1` when at least one source `failed` (this is what
turns a GitHub Actions run red); `2` for an operational error — the database was unreachable or
misconfigured before any source could even be attempted. A `2` always prints a fixed, safe
message and never the database URL or the underlying exception text, since either could embed a
password. A source skipped because it was already syncing is reported on its own line and does
not count toward the failure total.

## For docs/sources.md — new section, after "Failed and Partial Runs" (or operations.md's
equivalent; Opus should place it next to the existing run-summary docs):

## Source Health

Shown on the Sources page per source, and in `GET /api/sources` as `health`,
`consecutive_failures`, and `last_success_age_hours`. Derived on every read from
`last_success_at` and recent run history — nothing new is stored
([ADR-012 §11](decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md#11-source-health)).

| Health | Meaning |
|---|---|
| `disabled` | The source is turned off. |
| `never_run` | Never finished a sync. |
| `healthy` | Last succeeded (`success` or `no_change`) within 24 hours, and the latest finished run wasn't `partial`. |
| `warning` | Last succeeded 24–36 hours ago, or the latest finished run was `partial` with an otherwise-healthy success. |
| `stale` | Last succeeded more than 36 hours ago. |
| `failing` | The latest finished run was `failed`, or the source has never succeeded at all. |

The 24/36-hour thresholds give one full missed cycle of slack over the twice-daily production
schedule before a source is flagged past "warning". `consecutive_failures` counts `failed`/
`partial` runs since the last success, newest-first; a `success` or `no_change` run resets it to
zero. A source whose *latest* run is still `running` is judged by whichever run finished before
it — an in-progress sync never shows as `failing` just because it hasn't finished yet.
