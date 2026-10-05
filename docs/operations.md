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

Milestone 6 adds `.github/workflows/sync-production.yml`: `python -m app.cli sync-sources --scheduled` against Neon at 06:17 and 18:17 America/Los_Angeles, and on manual dispatch. It connects to Neon directly with the `PRODUCTION_DATABASE_URL` secret of the GitHub `production` environment (not through Render, so it doesn't wake Render), only on `main` of `dude297/internship-finder`, and never for pull requests or pushes ([ADR-009 amendment](decisions/ADR-009-hosted-deployment-architecture.md#amendment-2026-10-01-scheduled-source-sync-milestone-6)). Active since 2026-10-02: the `production` environment (deployment branches: `main` only) holds the secret (Neon pooled URL), and the first manual dispatch ([run 37077086322](https://github.com/dude297/internship-finder/actions/runs/37077086322)) was green. Without the secret, a run fails fast with "PRODUCTION_DATABASE_URL is empty". Local development has no scheduler.

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

Recommended cap on enabled Greenhouse/Lever/Ashby sources, to keep the twice-daily scheduled sync inside its 20-minute GitHub Actions limit: **50** (the largest size measured). The extrapolated ceiling is around 200. Before going past 50, re-measure the elapsed time of a real scheduled run (runbook step 13). Real measurement, 2026-10-04: 20 ATS boards + the feed, a scheduled-style run of 24.6 s ([run 37234279820](https://github.com/dude297/internship-finder/actions/runs/37234279820)); first syncs of new boards took 7.6–53.6 s each (one-time creation and evaluation).

### Milestone 8.1 measurements (2026-10-05)

Same harness, on the M8.1 branch: 50 ATS boards + feed — first sync 122.2 s (21,366 SQL statements; slower than the 2026-10-04 run on a busier machine), unchanged re-sync 5.7 s (918), failure + close re-sync 9.0 s (920); `discover()` 5 statements; **opportunity list 9 statements at 1,456 and 1,931 opportunities** (freshness adds 3 set-based statements, independent of page size; `test_list_statement_count_is_constant`). Mixed fleet 20 ATS + 10 SmartRecruiters + feed: first sync 78.7 s (612 detail requests, ≤ 100 per source), unchanged re-sync 4.2 s with zero detail requests. Workable and Pinpoint cost one request per source per run, like Greenhouse. (The harness's last assertion, on SmartRecruiters retry sleep order, fails because the harness doesn't stub M8's rotating detail refresh; it's a harness issue, not a product one.)

Activating the whole Direct Source Catalog would bring production to 26 + 33 = 59 direct sources, above the measured cap of 50. Activate in batches (largest-internship boards first), watch the scheduled run's elapsed time after each batch, and re-measure before passing 50.

## Milestone 8.1 activation notes (prepared, not executed)

Production stays on Milestone 8 until the owner approves. After merge: migrate Neon to `b7e3d9f1a2c4` (CHECK only; the M8 app is unaffected), deploy Render then Vercel, smoke (freshness badges, filters, Source Coverage independent metric, Verified Direct Sources list). Then, only with owner approval: `python -m app.cli scan-requirements` re-extracts every opportunity with `requirements-rules` v2 (read-only measurement on 2026-10-05: 18 → ~290 pending suggestions over 215 opportunities; reviewed decisions are kept, nothing is auto-accepted); add catalog sources in bounded batches from **Verified Direct Sources**.

## Milestone 7 production activation runbook (executed 2026-10-04)

Code release (merge, deploy) is separate from source activation (ADR-013 §9). Executed 2026-10-04 in two batches of 10 (20 ATS sources): description coverage 0.0% → 22.4%, ATS-backed 0 → 294, 88 feed postings deduplicated exactly as predicted, 4 pending suggestions, nothing closed, eligibility unchanged; the scheduled sync with 21 sources took 24.6 s. Full record: [deployment.md](deployment.md#milestone-7-release-2026-10-04). Use the same steps for any later batch.

1. Merge `feature/m7-provider-enrichment` to `main`.
2. Confirm CI is green on the merge commit.
3. Deploy: Render first, then Vercel, following the existing procedure in [deployment.md](deployment.md#deploy-order).
4. Run `python -m app.cli source-coverage` against production (read-only; no sources are created or synced by this step).
5. Open the Sources page's discovery/suggestions view and inspect what it offers.
6. Choose a bounded first batch of suggestions (for example, at most 10 boards, largest feed-only coverage first); leave scope **Internships only**.
7. Add the selected boards (`POST /api/sources/discovery/add`).
8. Sync each added source manually, one at a time.
9. Verify deduplication: counts in the run summary, no new duplicate opportunities, no unexpected closures.
10. Re-run `source-coverage` and record the description-coverage delta against step 4.
11. Count pending requirement suggestions created by the new syncs.
12. Leave every suggestion pending — accept none. The scheduled sync maintains them afterward.
13. Watch the next scheduled run's elapsed time against the 20-minute GitHub Actions limit, now that more sources are enabled.
14. Docs closeout: record what ran, the before/after coverage numbers, and the batch added, in PROJECT_STATE.md (lead) and here if operational behavior changed.

**Expected one-time side effect:** the first full feed sync after this release adds an `ashby:<board>:<posting>` identifier to feed postings that match an Ashby board (ADR-013 §2); about 60 Ashby-backed feed postings report as `updated` once, because the identifier is part of the content hash. This is normal — nothing closes, and no requirement-extraction fingerprint input changes.

**Rollback.** Disable a source rather than deleting it (toggle on the Sources page, or `UPDATE ingestion_sources SET enabled = false WHERE kind = '<kind>' AND identifier = '<board>'`): disabling stops future syncs and leaves its existing records and opportunities untouched. A disabled source's canonical text stays as the last-owned text until another source either falls back onto the opportunity or the opportunity closes (ADR-013 §5); nothing is deleted or rewritten by disabling alone.

## Milestone 8 release and activation (executed 2026-10-05)

Executed 2026-10-05: registry live (13 programs), 6 SmartRecruiters companies (AbbVie, Bosch, Eurofins, Wellmark, Keenfinity, LLNL), description coverage 22.4% → 38.7%, 18 pending suggestions (none accepted), scheduled sync 223.7 s with 28 sources. Full record: [deployment.md](deployment.md#milestone-8-release-2026-10-05). The steps below include the correction learned during that release.

**Release order** (migration `a8c3e5f7b9d1`; see [data-model.md](data-model.md#milestone-8-migration-a8c3e5f7b9d1) for the compatibility rules):

1. Disable the scheduled sync workflow for the window (`gh workflow disable sync-production.yml`): the migration seeds a `curated_registry` source the Milestone 7.1 code can't read, so a scheduled run between migrate and deploy would fail.
2. Merge; confirm CI green on the merge commit.
3. Migrate Neon to `a8c3e5f7b9d1`, then deploy Render immediately, then Vercel (the 7.1 bundle rejects a source list containing the registry). Hard-reload open tabs.
4. Hosted smoke; re-enable the workflow.

**Activation** (owner-approved, bounded, like the Milestone 7 runbook):

1. `source-coverage` before (read-only).
2. **Sync the discovery feed once on Milestone 8 code before adding any SmartRecruiters source** (expect ~40 `updated`, 0 errors). Feed records imported by older code don't yet carry the `smartrecruiters:` identifier, so a SmartRecruiters source synced first creates duplicates of those postings (they then make the feed sync raise identity conflicts). This happened on 2026-10-05 and was repaired (see deployment.md); the same rule applies to any future provider whose feed identity is added by a release.
3. Sync the built-in **Curated Program Registry** once manually: expect 13 created, run `success`, and only verified dates in deadline columns. Programs needing date verification show the badge from their `verify_by` date.
4. From Suggested Sources, add a bounded batch of SmartRecruiters companies (Internships only); sync each manually. A first sync may be `partial` if a company has more than 100 internship postings needing detail (nothing closes; later runs finish it).
5. Verify deduplication (feed postings attach to the SmartRecruiters record, no duplicates, no closures), `source-coverage` after, count pending suggestions, accept none.

**Expected one-time side effect:** the first feed sync after the release adds a `smartrecruiters:<company>:<id>` identifier to the ~40 feed postings that name a SmartRecruiters posting, so they report as `updated` once (the identifier is part of the content hash). No requirement-extraction input changes and nothing closes. Items of every other source hash exactly as before (the new registry date fields are left out of the hash while unset).

**Request bound:** a SmartRecruiters source makes at most 50 list + 100 detail requests per run (each with the HTTP client's ≤ 3 attempts); the registry makes none. The ADR-013 cap of 50 enabled ATS sources still applies, SmartRecruiters included.

**Measured (2026-10-04, `scripts/perf_sources.py --sr`, local Docker PostgreSQL 18, all HTTP mocked):** 20 Greenhouse/Lever/Ashby boards + 10 SmartRecruiters sources (small, 100-posting, and 500-posting multi-page boards, Internships only) + a 1,000-item feed. First sync (1,986 created): 90.5 s, 22 SmartRecruiters list and 612 detail requests in total, at most 5 list / 100 detail per source. Unchanged re-sync: 6.8 s, 22 list and **0** detail requests, all 31 runs `success`. With failing details and a 429 (`Retry-After`): 14.1 s, the failing board `partial` with nothing closed, the rate-limited board `success` after one retry. Elapsed time is dominated by database work on first creation, not requests.

**Large companies:** a company with hundreds of internship titles (Bosch: 391 of 4,832 postings, 49 list pages) fills over several runs at 100 details each; those runs are `partial`, close nothing, and Source Health shows the source as `failing` until the backlog is fetched. A company over 5,000 postings fails every run (closes nothing); disable it. Prefer companies whose feed coverage justifies the runtime (Bosch ≈ 165–230 s per run).

**Rollback:** disable a SmartRecruiters source or the registry to stop its syncs (records and opportunities stay). Rolling code back to Milestone 7.1 needs the schema downgraded first, which refuses while SmartRecruiters sources or registry records exist: delete those sources' records/opportunities deliberately (or keep the Milestone 8 code).

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
