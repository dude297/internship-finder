# Operations

The app runs locally and, since Milestone 3.5, hosted on Vercel → Render → Neon ([deployment.md](deployment.md), [ADR-009](decisions/ADR-009-hosted-deployment-architecture.md)). There are no scheduled jobs or monitoring. Each section is labeled planned or implemented.

## Owner Account and Sessions (implemented, local)

- Create the owner once: `python -m app.cli create-owner --username <name>` (password via `getpass`).
- Rotate the password: `python -m app.cli set-password --username <name>`. This revokes every session of that user.
- Sessions expire after `SESSION_TTL_HOURS` (default 24). Logout deletes the session row. Expired rows are removed the next time the user logs in; there's no background cleanup yet.
- Disable an account without deleting data: `UPDATE auth_users SET is_active = false WHERE username = '<name>'` (its sessions stop working immediately).
- Failed logins are throttled in memory: 10 per client key and 50 in total per sliding 15 minutes, checked before any password work. There are two buckets: requests carrying the Vercel proxy secret share `proxy`, and everything else (direct Render calls, local development) shares `direct`; forwarding headers are never read, because Vercel sometimes passes client-forged ones through. Ten failed attempts through the site block new logins for everyone for up to 15 minutes (existing sessions keep working); wait it out or redeploy Render to clear it ([ADR-009 §6](decisions/ADR-009-hosted-deployment-architecture.md#6-login-rate-limiting-behind-the-proxy)). A restart or deploy clears the counters. Argon2 hashing/verification runs at most 2 at a time.
- Nothing logs passwords, session tokens, CSRF tokens, or request bodies. Unexpected errors are logged server-side with their stack trace; clients get a generic `500`.

## Local Database (implemented)

`compose.yaml` runs PostgreSQL 18 on `127.0.0.1:5432` with a named volume `pgdata`. That volume holds the owner's private data: back it up yourself if it matters (for example, `docker compose exec postgres pg_dump -U internship_finder internship_finder > backup.sql`, stored **outside** the repository). `docker compose down -v` deletes it.

## Source Sync (implemented: manual, plus a scheduled production workflow)

Sources sync when the owner asks: **Sync now** / **Sync all** on the Sources page, `POST /api/sources/{id}/sync` / `POST /api/sources/sync`, or `python -m app.cli sync-source <id-or-key>` / `sync-sources`. All use the same pipeline ([ADR-008](decisions/ADR-008-opportunity-ingestion-and-deduplication.md)).

Milestone 6 adds `.github/workflows/sync-production.yml`: `python -m app.cli sync-sources --scheduled` against Neon at 06:17 and 18:17 America/Los_Angeles, and on manual dispatch. It connects to Neon directly with the `PRODUCTION_DATABASE_URL` secret of the GitHub `production` environment (not through Render, so it doesn't wake Render), only on `main` of `dude297/internship-finder`, and never for pull requests or pushes ([ADR-009 amendment](decisions/ADR-009-hosted-deployment-architecture.md#amendment-2026-10-01-scheduled-source-sync-milestone-6)). **It does nothing until that environment secret exists**: until then each run fails fast with "PRODUCTION_DATABASE_URL is empty". Local development has no scheduler.

- **CLI exit codes** (`sync-sources`, `sync-source`): `0` every attempted source finished `success`, `no_change`, or `partial`; `1` at least one `failed` (turns the workflow run red); `2` the database was unreachable or misconfigured (a fixed message, never the URL or the exception text), or, with `--scheduled`, its schema isn't at the code's migration head. A source skipped because it was already syncing gets its own line and isn't a failure. Output is per-source counts and elapsed time plus one aggregate line.
- **Inactivity.** GitHub disables scheduled workflows in a public repository after 60 days without repository activity. Nothing alerts; Source Health turns `stale` after 36 h. Recovery: re-enable the workflow on the Actions tab (or `gh workflow enable sync-production.yml`) and dispatch it once.
- **Concurrency.** A scheduled run and a manual sync of the same source are arbitrated by the per-source running-run index, exactly like two manual syncs. The workflow's `concurrency` group only stops overlapping workflow runs.

Measured locally on 2026-09-27 against the live discovery feed (disposable database, synthetic profile, Windows + Docker PostgreSQL 18): the first sync of 1,034 postings took about 22 s (including one evaluation per posting); a repeat answered `304` in under 0.5 s; a forced full re-process (validators cleared) found all 1,034 unchanged in under 1 s. A 50-item page of the opportunity list took 30–130 ms at ~1,100 opportunities.

## Source Health (implemented, Milestone 6)

The Sources page and `GET /api/sources` report `health`, `consecutive_failures`, and `last_success_age_hours` per source, derived on every read from `last_success_at` and run history (nothing stored; `app/services/source_health.py`):

| Health | Meaning |
|---|---|
| `disabled` | The source is turned off |
| `never_run` | No finished run yet |
| `healthy` | Last success (`success` or `no_change`) within 24 h, and the latest finished run wasn't `partial` |
| `warning` | Last success 24–36 h ago, or the latest finished run was `partial` |
| `stale` | Last success more than 36 h ago |
| `failing` | The latest finished run `failed`, or it has never succeeded |

24/36 h gives one missed twice-daily cycle of slack before escalating past `warning`. `consecutive_failures` counts `failed`/`partial` runs since the last success; a success resets it. A run still `running` is judged by the run that finished before it. No alerts, email, or push. A source whose every run ends `partial` (for example a persistent identity conflict) never refreshes `last_success_at`, so it drifts to `stale` (or `failing` if it never succeeded) and its failure count keeps growing: that's intended, since a partial run never closes postings and needs attention.

## Requirement Candidate Scan (implemented, Milestone 6; not run in production yet)

`python -m app.cli scan-requirements [--batch-size 200]` runs the deterministic requirement extractor over every stored opportunity whose `requirement_extraction_fingerprint` isn't current, in keyset batches committed one at a time ([ADR-012 §9](decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md#9-catalog-scan)). Idempotent and safe to rerun or interrupt: it only creates or refreshes *pending suggestions*. It never accepts, never changes an assessment status, never marks anything stale, and never evaluates. Output is counts only; exit `2` on a database error. Measured on 1,100 synthetic opportunities (local Docker PostgreSQL 18, 2026-10-02): 13.3 s and 1,357 SQL statements cold (623 suggestions), 0.95 s and 37 statements on a rerun. Production runs it only after explicit release approval.

## Run Summaries (implemented)

Every sync records an `ingestion_runs` row: status (`running`, `success`, `partial`, `failed`, `no_change`), start/finish time, the source's own snapshot time, and counts (fetched, filtered by the source's scope, normalized, created, updated, deduplicated, unchanged, closed, reactivated, invalid, errors). Up to 100 safe per-item errors are stored per run (stage, short code, message, source item ID). The Sources page shows each source's latest run; `GET /api/sources/{id}/runs` lists recent ones. Each finished run is also logged as one line with the source key and counts. No payloads, headers, or stack traces are stored or returned.

## Failed and Partial Runs (implemented)

- One failing source doesn't stop the others in "sync all".
- `failed` (network error, timeout, rate limit longer than 30 s, HTTP error, oversized or non-JSON response, unexpected format, incomplete snapshot): nothing is changed. The reason is on the run. Fix or wait, then sync again.
- `partial` (some items invalid or conflicting): valid items are imported, but nothing is closed, and the HTTP validators aren't stored, so the next sync fetches the full snapshot again. A recurring partial run (for example, a persistent identity conflict) means that source's missing postings won't close until it's resolved; the run's problems list names the items.
- Only one sync of a source can run at a time: a partial unique index allows one `running` run per source, so a concurrent second start gets "already syncing" (`409` from the API). Different sources can sync concurrently.
- A run left `running` (e.g. the process stopped mid-sync) is marked `failed` by the next sync of that source after 15 minutes; until then that source reports "already syncing".
- Retries: at most 3 attempts per request on timeouts, connection errors, 429, and 5xx, with short backoff. There's no alerting; check the Sources page.

## Board Scope Changes (implemented)

Switching a Greenhouse/Lever board between **Internships only** and **All postings** takes effect on its next sync: the change clears the HTTP validators, so that sync fetches the whole board, closes postings the new scope excludes, and reopens ones it admits again ([sources.md](sources.md#board-scope-internships-only-greenhouse-and-lever)). A partial run closes nothing, as always.

## Closed Postings (implemented)

When a complete successful sync no longer lists a posting, its source record is marked closed (`is_active = false`, `closed_at`). Nothing is deleted: the opportunity, its evaluations, and its application tracking stay. An opportunity is shown as **closed** when all of its automated source records are closed; the default list view hides closed postings, and **Show → Closed postings / Everything** finds them. If the posting reappears, the record reopens. There's no age-based "stale" rule.

## Database Backup Considerations (planned)

Not configured yet. The selected provider is Neon Free ([ADR-004](decisions/ADR-004-technology-stack.md)); its free-tier history/restore window is limited, so the plan must include a free, self-run backup (e.g. a scheduled `pg_dump`). It must cover backup frequency, retention, and a tested restore procedure.

## Logs (planned)

Structured logs as described in [ENGINEERING_GUIDELINES.md §11](../ENGINEERING_GUIDELINES.md#11-logging-and-observability). No secrets, and no unnecessary sensitive profile data. The log destination is TBD.

## Evaluation History and Re-evaluation (implemented; not scheduled)

`app.repositories` appends `opportunity_evaluations` rows with their rule results. Earlier rows are kept as history, and the latest `evaluated_at` is current. Evaluations run:

- when an opportunity is created or updated by hand or by a sync (if a profile exists), **only if** its eligibility or fit inputs changed since the latest evaluation (two SHA-256 fingerprints, [ADR-010 §8](decisions/ADR-010-fit-scoring-v1.md#8-persistence-and-fingerprints)), so unchanged syncs and edits of other fields add nothing
- in **one catalog pass** when the profile is saved with a changed eligibility input (education timeline, date of birth, citizenships) or the Match Profile is saved, in the same transaction; the pass appends rows only for opportunities whose inputs changed
- on demand, always: `POST /api/opportunities/{id}/evaluate`

Every row since Milestone 4 carries eligibility and fit. Rows from before have NULL fit; the first Match Profile save after upgrading scores them (until then the recommended order falls back to eligibility, then newest).

**Catalog pass performance** ([ADR-010 §9](decisions/ADR-010-fit-scoring-v1.md#9-catalog-re-evaluation-stays-synchronous)). The pass reads every latest fingerprint in one query, loads opportunities in keyset batches of 200 with their requirements, skips unchanged pairs, and flushes once per batch, so it issues a few dozen SQL statements regardless of catalog size. Measured 2026-09-29 (Windows, Docker PostgreSQL 18, local) and hosted (Render Free / Neon Free, 1,055 real opportunities, through Vercel):

| Operation | ~1,100 synthetic opportunities (`scripts/perf_smoke.py`, local) | 1,050 live discovery-feed postings (disposable DB, local) | 1,055 hosted opportunities (production, 2026-09-29) |
|---|---|---|---|
| First Match Profile save (scores everything) | 2.14 s, 32 SQL statements | 1.34 s | 6.359 s (evaluated 1,055 / unchanged 0) |
| Unchanged Match Profile save | 0.30 s, 17 statements | 0.16 s | 1.995 s (evaluated 0 / unchanged 1,055) |
| Changed Match Profile save | 2.25 s, 31 statements | 1.20 s | 6.391 s (evaluated 1,055 / unchanged 0) |
| Recommended list page (50) | 0.05 s, 5 statements | 0.06 s | 0.216 s |
| Recommended list page (100) | — | — | 0.306 s |

The Milestone 3 path (a forced row per opportunity, one flush each) took ~4 s locally and ~10 s hosted for the same size. Batch size barely changes the time (50 to 1,100 all within noise) but bounds memory (traced peak ~9 MB at 50, ~13 MB at 200, ~33 MB unbatched), so 200 is kept. Hosted timings (Render Free/Neon, cold network hop plus Vercel's proxy) run a few times the local ones, well under the proxy timeout; if a much larger catalog approaches it, background re-evaluation becomes a later-milestone requirement (no queue exists). Re-run with `PERF_DATABASE_URL=<disposable db> python scripts/perf_smoke.py` in `backend/`. History still grows with every real input change; pruning is TBD.

Still not automatic: re-evaluation when the eligibility rules version changes, and when time passes an expected graduation or enrollment date (see Future Scheduled Jobs).

## Migrations

Schema changes are Alembic migrations (`backend/alembic/versions/`), validated in CI against a disposable PostgreSQL. Locally, run `alembic upgrade head` after pulling new migrations. The hosted Neon database is migrated by hand from a trusted shell before the code that needs it is deployed, and never downgraded ([deployment.md](deployment.md#deploy-order)).

## Environment Configuration

Backend: `DATABASE_URL` (required for everything except `/api/health`), `SESSION_TTL_HOURS`, `SESSION_COOKIE_SECURE`, and hosted only `HOSTED`, `PROXY_SHARED_SECRET`. See [`backend/.env.example`](../backend/.env.example), [development.md](development.md#environment-variables), and [deployment.md](deployment.md).

## Incident Handling (planned)

For a single-user tool, the minimum is to detect the failure (run summary or error log), record it in [PROJECT_STATE.md](../PROJECT_STATE.md) → Known Bugs, fix it with a regression test, and note it in [CHANGELOG.md](../CHANGELOG.md).

## Future Scheduled Jobs (planned)

- Alerting on repeated `failed`/`partial` runs (scheduled sync and derived source health exist since Milestone 6; nothing alerts yet)
- Re-evaluation when eligibility rules or scoring version change, or when the user's projected education status crosses a date (graduation, enrollment)
- In-app alerts/digests (no email/SMS services initially)

Scheduler: GitHub Actions scheduled workflows (the source sync workflow exists since Milestone 6), or later a self-hosted runner. No paid scheduler. Workflows only orchestrate Python commands. If free-tier limits (Actions minutes, Neon compute, Render hours) are reached, jobs defer or fail visibly rather than incur charges ([ADR-004](decisions/ADR-004-technology-stack.md)).

## Maintenance

Update this file whenever runtime or monitoring behavior changes.
