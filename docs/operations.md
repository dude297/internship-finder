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

Milestone 6 adds `.github/workflows/sync-production.yml`: `python -m app.cli sync-sources --scheduled` against Neon at 06:17 and 18:17 America/Los_Angeles, and on manual dispatch. It connects to Neon directly with the `PRODUCTION_DATABASE_URL` secret of the GitHub `production` environment (not through Render, so it doesn't wake Render), only on `main` of `dude297/internship-finder`, and never for pull requests or pushes ([ADR-009 amendment](decisions/ADR-009-hosted-deployment-architecture.md#amendment-2026-10-01-scheduled-source-sync-milestone-6)). Active since 2026-10-02: the `production` environment (deployment branches: `main` only) holds the secret (Neon pooled URL), and the first manual dispatch ([run 37077086322](https://github.com/dude297/internship-finder/actions/runs/37077086322)) was green. Without the secret, a run fails fast with "PRODUCTION_DATABASE_URL is empty". The workflow installs the backend from the hash-locked `backend/requirements.lock` ([development.md](development.md#dependency-lock)), so every scheduled run uses the same dependency versions as CI. Local development has no scheduler.

- **Public logs.** Workflow logs of this public repository are public. CLI commands log warnings and errors without tracebacks (an exception is reduced to its class name), and the database engine never renders bound parameters (`hide_parameters`), so neither the database host nor profile-derived values reach the log.
- **CLI exit codes** (`sync-sources`, `sync-source`): `0` every attempted source finished `success`, `no_change`, or `partial`; `1` at least one `failed` (turns the workflow run red); `2` the database was unreachable or misconfigured (a fixed message, never the URL or the exception text), or, with `--scheduled`, its schema isn't at the code's migration head. A source skipped because it was already syncing gets its own line and isn't a failure. Output is per-source counts and elapsed time plus one aggregate line.
- **Inactivity.** GitHub disables scheduled workflows in a public repository after 60 days without repository activity. Nothing alerts; Source Health turns `stale` after 36 h. Recovery: re-enable the workflow on the Actions tab (or `gh workflow enable sync-production.yml`) and dispatch it once.
- **Concurrency.** A scheduled run and a manual sync of the same source are arbitrated by the per-source running-run index, exactly like two manual syncs. The workflow's `concurrency` group only stops overlapping workflow runs.

Measured locally on 2026-09-27 against the live discovery feed (disposable database, synthetic profile, Windows + Docker PostgreSQL 18): the first sync of 1,034 postings took about 22 s (including one evaluation per posting); a repeat answered `304` in under 0.5 s; a forced full re-process (validators cleared) found all 1,034 unchanged in under 1 s. A 50-item page of the opportunity list took 30–130 ms at ~1,100 opportunities.

## Source Coverage (implemented, Milestone 7)

`python -m app.cli source-coverage` and the Sources page's coverage section report, derived on read over open opportunities (nothing stored, [ADR-013 §2](decisions/ADR-013-provider-enrichment-and-source-authority.md#2-ats-source-discovery)):

- **Description coverage %**: active opportunities with a non-empty canonical description, over all active opportunities.
- **ATS-backed**: active opportunities with an active record from a direct ATS source (Greenhouse, Lever, Ashby, SmartRecruiters).
- **Feed-only**: active opportunities whose only active automated records are from the discovery feed.
- **Enrichable**: feed-only opportunities whose feed record proves a supported provider identity a source suggestion covers.

Description coverage is the operational KPI this milestone introduces: it's the number a bounded first batch of added boards should move (see the runbook below).

Scheduled and manual syncs order direct ATS sources before the discovery feed (within each group, oldest source first, then ID), so a feed sync within one run sees the boards' current state; correctness doesn't depend on this ordering ([ADR-013 §5](decisions/ADR-013-provider-enrichment-and-source-authority.md#5-fallback-when-a-direct-ats-source-closes), [ADR-013 §7](decisions/ADR-013-provider-enrichment-and-source-authority.md#7-scheduled-sync-ordering)). One source failing never stops the others; the per-source running-run index stays the only concurrency guard.

### Operational source cap

Measured on 2026-10-04 with `scripts/perf_sources.py` (manual, never in CI): a disposable local database (Windows + Docker PostgreSQL 18), N synthetic Greenhouse/Lever/Ashby boards of 20 internship postings each, plus a synthetic 1,000-item discovery feed with one posting deduplicating onto each board. All HTTP is mocked, so these times are database and pipeline cost only.

| ATS sources (+ feed) | First sync (creates ~1,200–1,950) | Unchanged re-sync | Re-sync with one source failing (500) and one closing all postings | SQL statements per sync |
|---|---|---|---|---|
| 10 | 40.8 s | 1.3 s | 4.3 s | 132 |
| 25 | 47.7 s | 2.2 s | 5.6 s | 312 |
| 50 | 57.8 s | 3.2 s | 17.6 s | 612 |

At every size: ATS sources ran before the feed, the canonical owner didn't change across the unchanged re-sync, the failing source produced one failed run without stopping the others, and the closing board's 20 postings fell back onto the feed (ADR-013 §5). `discover()` used 3 SQL statements (~40 ms over ~1,950 opportunities) and an opportunity list page 6, independent of N. The first-sync time is dominated by creating and evaluating ~1,000 feed postings, a one-time cost.

Real network fetches add roughly 1–3 s per board, so a scheduled run with 50 boards is about 1–3 minutes plus the feed sync.

Recommended cap on enabled Greenhouse/Lever/Ashby sources, to keep the twice-daily scheduled sync inside its 20-minute GitHub Actions limit: **50** (the largest size measured). The extrapolated ceiling is around 200. Before going past 50, re-measure the elapsed time of a real scheduled run ([source activation](#source-activation-procedure), step 6). Real measurement, 2026-10-04: 20 ATS boards + the feed, a scheduled-style run of 24.6 s ([run 37234279820](https://github.com/dude297/internship-finder/actions/runs/37234279820)); first syncs of new boards took 7.6–53.6 s each (one-time creation and evaluation).

### Milestone 8.1 measurements (2026-10-05)

Same harness, on the M8.1 branch: 50 ATS boards + feed — first sync 122.2 s (21,366 SQL statements; slower than the 2026-10-04 run on a busier machine), unchanged re-sync 5.7 s (918), failure + close re-sync 9.0 s (920); `discover()` 5 statements; **opportunity list 9 statements at 1,456 and 1,931 opportunities** (freshness adds 3 set-based statements, independent of page size; `test_list_statement_count_is_constant`). Mixed fleet 20 ATS + 10 SmartRecruiters + feed: first sync 78.7 s (612 detail requests, ≤ 100 per source), unchanged re-sync 4.2 s with zero detail requests. Workable and Pinpoint cost one request per source per run, like Greenhouse. (The harness's last assertion, on SmartRecruiters retry sleep order, fails because the harness doesn't stub M8's rotating detail refresh; it's a harness issue, not a product one.)

Activating the whole Direct Source Catalog would bring production to 26 + 33 = 59 direct sources, above the measured cap of 50. Activate in batches (largest-internship boards first), watch the scheduled run's elapsed time after each batch, and re-measure before passing 50.

## Source Activation Procedure

Adding production sources after a release (new boards, a catalog batch, a new provider) is an owner-approved step, done in bounded batches:

1. `python -m app.cli source-coverage` before (read-only).
2. **If the release added a feed identity** (a new `provider_identity` rule), sync the discovery feed once on the new code *before* adding sources of that provider; otherwise the first board sync creates duplicates of feed postings that lack the new identifier.
3. Add the batch (Sources page → Suggested Sources or **Verified Direct Sources**; Internships only). Keep enabled direct sources at or under the [operational cap](#operational-source-cap).
4. Sync each new source manually; check deduplication (feed postings attach to the board record), no closures, no identity conflicts.
5. `source-coverage` after; count pending requirement suggestions; accept none automatically.
6. Watch the next scheduled run's elapsed time against the 20-minute limit.
7. Record the batch and the before/after numbers in the release record.

**Rollback:** disable a source (Sources page toggle) rather than deleting it; its records and opportunities stay, and nothing is rewritten by disabling alone.

## Retiring a Source and Feed-Free Start (implemented, Milestone 8.2, ADR-016)

Disabling a source alone leaves its records active (its postings stay open as `source_warning`). To retire one properly, from `backend/` with `DATABASE_URL` set:

1. `python -m app.cli source-coverage` (read-only) for the before numbers.
2. `python -m app.cli retire-source <key-or-id>` (dry run; changes nothing). Read the counts: records closed, opportunities closed, stayed open via another source, fallbacks, curated preserved. Production runs are owner-approved.
3. `python -m app.cli retire-source <key-or-id> --apply`. It refuses (exit 1) while the source is syncing (a `running` run older than 15 minutes is treated as dead); wait and retry. A scheduled sync that started before the retirement skips the source on its turn. A failure leaves the source enabled and nothing closed. Re-running is a no-op.
4. `source-coverage` after; the opportunities closed should match the dry run.

**Rollback:** re-enable the source (Sources page) and sync it. Validators were cleared, so the sync is a full snapshot and reopens the records. Nothing was deleted.

**New installation without the feed:** after `alembic upgrade head` and `create-owner`, run `python -m app.cli bootstrap-sources --tags <tag> --disable-feed --dry-run`, then without `--dry-run`, then `sync-sources` (or pass `--sync`). It adds catalog boards through the same path as the catalog add API, refuses beyond 50 enabled direct sources, and never syncs unless `--sync`. It does not re-enable a configured but disabled entry. Curated opportunities keep their content; one closes if no active source remains. On an installation whose feed already has open postings, use `retire-source` instead of `--disable-feed`.

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

## Requirement Candidate Scan (implemented, Milestone 6; run in production 2026-10-02)

`python -m app.cli scan-requirements [--batch-size 200]` runs the deterministic requirement extractor over every stored opportunity whose `requirement_extraction_fingerprint` isn't current, in keyset batches committed one at a time ([ADR-012 §9](decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md#9-catalog-scan)). Idempotent and safe to rerun or interrupt: it only creates or refreshes *pending suggestions*. It never accepts, never changes an assessment status, never marks anything stale, and never evaluates. Output is counts only; exit `2` on a database error. Measured on 1,100 synthetic opportunities (local Docker PostgreSQL 18, 2026-10-02): 13.3 s and 1,357 SQL statements cold (623 suggestions), 0.95 s and 37 statements on a rerun. Production run (2026-10-02, after the release): 1,193 scanned, 1,050 refreshed, 143 unchanged (already fingerprinted by the first scheduled sync), 0 failed, 0 suggestions, 92.9 s. Zero because every production opportunity comes from the discovery feed, which has no description field; extraction then sees only the title. Requirement rows, evaluations, assessment statuses, and eligibility were verified unchanged (per-opportunity digests). Suggestions appear once a board source with descriptions (Greenhouse, Lever, Ashby) is added; new and changed postings are extracted during sync, so no rescan is needed for them.

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

Switching a Greenhouse/Lever board between **Internships only** and **All postings** takes effect on its next sync: the change clears the HTTP validators, so that sync fetches the whole board, closes postings the new scope excludes, and reopens ones it admits again ([sources.md](sources.md#board-scope-internships-only-every-ats-board)). A partial run closes nothing, as always.

## Closed Postings (implemented)

When a complete successful sync no longer lists a posting, its source record is marked closed (`is_active = false`, `closed_at`). Nothing is deleted: the opportunity, its evaluations, and its application tracking stay. An opportunity is shown as **closed** when all of its automated source records are closed; the default list view hides closed postings, and **Show → Closed postings / Everything** finds them. If the posting reappears, the record reopens. There's no age-based "stale" rule.

## Database Backup (implemented; not activated until the owner configures it)

[ADR-021](decisions/ADR-021-encrypted-backups.md). `.github/workflows/backup-production.yml` runs weekly (Sundays 09:43 UTC) and on manual dispatch, only on `main` of `dude297/internship-finder`, in the `production` environment. It runs `scripts/backup_db.sh`, which streams `pg_dump --format=custom | age -r <public key>` into a file (no plaintext on disk or in logs) and uploads it as the artifact `db-backup-<run id>` with **14-day retention**. The workflow holds only the *public* age key; the private key stays with the owner.

**Artifacts of this public repository are downloadable by any signed-in GitHub user.** That is why the backup is encrypted before upload, why the file name is only `backup-YYYYMMDD.dump.age`, and why retention is bounded. Treat the decrypted dump as exactly as sensitive as the database (it includes the profile and auth tables).

Without the `BACKUP_AGE_RECIPIENT` variable (or the `PRODUCTION_DATABASE_URL` secret) the first step fails with a fixed message and nothing touches the database.

### Owner activation (once)

1. On a trusted machine install [age](https://github.com/FiloSottile/age) and run `age-keygen -o internship-finder-backup.key`. It prints `Public key: age1...`.
2. Store the private key file in a password manager **and** one offline copy. Never commit it, paste it into chat, or put it in GitHub. Losing it makes every backup unreadable.
3. Set the public key as a repository variable (not a secret): `gh variable set BACKUP_AGE_RECIPIENT --body "age1..."` (or Settings, Secrets and variables, Actions, Variables). An environment variable on `production` also works.
4. Dispatch once: `gh workflow run backup-production.yml --ref main`, and confirm it is green and the artifact exists.
5. Test a restore (below) into a local or new Neon database before relying on it.

### Restore runbook

1. Download the artifact: `gh run download <run-id> -n db-backup-<run-id>` (or from the run page), giving `backup-YYYYMMDD.dump.age`.
2. Create a disposable target: a local database (`docker compose exec -T postgres psql -U internship_finder -c "CREATE DATABASE restore_check"`) or a **new Neon branch** (Neon console; never the production branch). You need `age`, `pg_restore`, and `psql` (PostgreSQL 18 client tools) on your PATH.
3. Restore:

   ```bash
   AGE_IDENTITY=/path/to/internship-finder-backup.key \
   RESTORE_DATABASE_URL='postgresql://user:pass@host/db?sslmode=require' \
   scripts/restore_backup.sh backup-YYYYMMDD.dump.age
   ```

   The script decrypts with `age -d -i <key> | pg_restore --no-owner --no-privileges --exit-on-error`, and **refuses a target that already has tables**, so it can't overwrite anything.
4. Verify: the script prints the `alembic_version` and row counts (opportunities, source records, sources, profiles). Also run `alembic current` from `backend/` with `DATABASE_URL` set to the restored database (it must report the head revision), and compare the counts with the live database.
5. **Replacing production is a separate, owner-only decision**, never part of this script: pause the scheduled sync, take a fresh backup, restore into a new Neon branch, verify, then point `DATABASE_URL` (Render and the `production` environment secret) at it. Don't drop anything in the production branch.

Verified locally on 2026-10-06 against disposable PostgreSQL 18 databases: migrate to head, insert synthetic rows, dump and encrypt (58 KB, no table names or row text in the file), decrypt and restore into an empty database; row counts and `alembic current` matched. A non-empty target and a wrong key were both refused, and a failing `pg_dump` left no file.

Inactivity: like the sync, GitHub disables scheduled workflows after 60 days without repository activity. Re-enable it (`gh workflow enable backup-production.yml`) and dispatch once. The local Docker database (`pgdata` volume) is still the owner's own `pg_dump` ([Local Database](#local-database-implemented)).

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

**Staleness and `reevaluate`** ([ADR-018](decisions/ADR-018-evaluation-staleness.md)). The rules and scoring versions are part of the fingerprints, so bumping `RULES_VERSION` or `SCORING_VERSION` makes every opportunity stale. Time passing never makes an evaluation stale: the education status and age are resolved at each requirement's reference date, never at today. Nothing runs the pass by itself after a version bump; it runs on a profile or Match Profile save, or:

```
python -m app.cli reevaluate [--stale-only] [--dry-run] [--batch-size 200]
```

It runs the same batched catalog pass for the owner's profile (keyset batches, one transaction), appends a row only for stale opportunities, prints counts only (`evaluated N, unchanged M`; `would evaluate` with `--dry-run`), and exits `2` on a database error. `--stale-only` is accepted and is the only mode. Run `--dry-run`, then the real command, after deploying a release that bumps a version ([deployment.md](deployment.md#release-procedure)); it appends one row per opportunity (about 2,000 at current size, a few seconds, like a changed Match Profile save above). Exit `1` means an unexpected failure (the class name is printed, never the message). It is not scheduled and the sync workflow is unchanged.

## Migrations

Schema changes are Alembic migrations (`backend/alembic/versions/`), validated in CI against a disposable PostgreSQL. Locally, run `alembic upgrade head` after pulling new migrations. The hosted Neon database is migrated by hand from a trusted shell before the code that needs it is deployed, and never downgraded ([deployment.md](deployment.md#deploy-order)).

## Environment Configuration

Backend: `DATABASE_URL` (required for everything except `/api/health`), `SESSION_TTL_HOURS`, `SESSION_COOKIE_SECURE`, and hosted only `HOSTED`, `PROXY_SHARED_SECRET`. See [`backend/.env.example`](../backend/.env.example), [development.md](development.md#environment-variables), and [deployment.md](deployment.md).

## Incident Handling (planned)

For a single-user tool, the minimum is to detect the failure (run summary or error log), record it in [PROJECT_STATE.md](../PROJECT_STATE.md) → Known Bugs, fix it with a regression test, and note it in [CHANGELOG.md](../CHANGELOG.md).

## Future Scheduled Jobs (planned)

- Alerting on repeated `failed`/`partial` runs (scheduled sync and derived source health exist since Milestone 6; nothing alerts yet)
- In-app alerts/digests (no email/SMS services initially)

Scheduler: GitHub Actions scheduled workflows (the source sync workflow exists since Milestone 6), or later a self-hosted runner. No paid scheduler. Workflows only orchestrate Python commands. If free-tier limits (Actions minutes, Neon compute, Render hours) are reached, jobs defer or fail visibly rather than incur charges ([ADR-004](decisions/ADR-004-technology-stack.md)).

## Maintenance

Update this file whenever runtime or monitoring behavior changes.
