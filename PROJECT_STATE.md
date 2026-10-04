# Project State

> `PROJECT_STATE.md` must be updated after every meaningful implementation milestone or architecture change.

Last Updated: 2026-10-04
Current Milestone: **Milestone 7 — Provider Enrichment + Source Coverage implemented on `feature/m7-provider-enrichment`, awaiting review (not merged, not deployed)** ([ADR-013](docs/decisions/ADR-013-provider-enrichment-and-source-authority.md)). **Milestone 6 — Requirement Intelligence + Automation complete; merged via [PR #13](https://github.com/dude297/internship-finder/pull/13) and released from `main` on 2026-10-02** ([ADR-012](docs/decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)), including the Milestone 5.1 fixes. Milestone 5 — Private Profile Source Ingestion + Review complete; merged via [PR #11](https://github.com/dude297/internship-finder/pull/11) ([ADR-011](docs/decisions/ADR-011-profile-source-ingestion-and-review.md)). Milestone 4 — Profile Intelligence + Fit Ranking v1 complete; merged via [PR #9](https://github.com/dude297/internship-finder/pull/9) ([ADR-010](docs/decisions/ADR-010-fit-scoring-v1.md)). Milestone 3.5 — Hosted Deployment Foundation complete; merged via [PR #7](https://github.com/dude297/internship-finder/pull/7). Milestone 3 — Automated Opportunity Discovery and Ingestion complete; merged via [PR #6](https://github.com/dude297/internship-finder/pull/6). Milestone 2 complete ([PR #5](https://github.com/dude297/internship-finder/pull/5)). Milestone 1 complete ([PR #4](https://github.com/dude297/internship-finder/pull/4)). Milestone 0 complete ([PR #2](https://github.com/dude297/internship-finder/pull/2)).
Current Production Version: `main` at `80257c5` on https://internship-finder-pi.vercel.app (Neon `e6d1a4b8c2f9`; Render deploy `dep-db03iknavr4c73e10b8g` live 2026-10-02 23:09 UTC; Vercel production deployment `dpl_8kqCpb15vP5q1rcJpsSB3Pvt6XJk` created 2026-10-02 23:11 UTC from a clean checkout of `80257c5` via CLI; hosted smoke passed 2026-10-02; scheduled source sync active)
Active Development Branch: `feature/m7-provider-enrichment` (Milestone 7; final PR to `main` open for review). Remote: https://github.com/dude297/internship-finder.

## Repository Visibility

| | |
|---|---|
| Repository visibility | **Public** (set on GitHub 2026-09-25) |
| Public repository safety | **Active** ([CLAUDE.md](CLAUDE.md#public-repository-safety), [ENGINEERING_GUIDELINES.md §16](ENGINEERING_GUIDELINES.md#16-public-repository-security-and-privacy)) |
| Private user data in Git | **Prohibited** |

Real résumé, transcript, profile, and application documents stay outside the repository, in the database or gitignored local storage. The owner's real profile is entered only through the running app. Downloaded source payloads are never committed; tests use fabricated provider fixtures.

## Current Objective

Milestone 7 (provider enrichment + source coverage) is released (2026-10-04) and activated: production runs `main` `bc23629` with 20 direct ATS boards, and description coverage rose from 0.0% to 22.4%. Milestone 7.1 (volunteer opportunity type) is released too (2026-10-04): production runs `main` `0a636e2`, Neon at `f2a7c9d4e1b3`.

## Status Summary

Terms: **Selected** = decided in an ADR. **Scaffolded/Implemented** = code exists in the repository and is tested. **Provisioned** = account/project/resource actually created. **Deployed** = running in a hosted environment.

| Area | Status |
|---|---|
| Technology stack | **Selected** ([ADR-004](docs/decisions/ADR-004-technology-stack.md)); hosting per [ADR-009](docs/decisions/ADR-009-hosted-deployment-architecture.md). **Provisioned and deployed** (Vercel Hobby → Render Free → Neon Free) from `main`. |
| Source/profile strategy | **Selected** ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)). Opportunity ingestion implemented (ADR-008). Résumé parser `resume-sections` v1 (ADR-011). |
| Core domain persistence | **Implemented** ([ADR-006](docs/decisions/ADR-006-core-domain-persistence-model.md), migration `3b9c6b57bb60`, immutable) |
| Authentication / private API | **Implemented and hosted** ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md), migration `7d7f4f8b9a3c`, immutable; hardened by [ADR-009](docs/decisions/ADR-009-hosted-deployment-architecture.md) §6–§7) |
| Opportunity ingestion | **Implemented and deployed** ([ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md), migration `726372d627b8`). Since Milestone 6: Ashby boards (no production Ashby source), a scheduled GitHub Actions sync (active since 2026-10-02), derived source health ([ADR-012](docs/decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)) |
| Requirement suggestions and review | **Implemented and deployed** (`requirements-rules` v1, migration `e6d1a4b8c2f9`, applied to Neon 2026-10-02; [ADR-012](docs/decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)). Suggestions never affect eligibility until accepted |
| Eligibility | **Implemented** v1 (rules version `v1`), evaluated automatically (only when inputs change) |
| Fit scoring and ranking | **Implemented and deployed** (scoring `v1`, [ADR-010](docs/decisions/ADR-010-fit-scoring-v1.md), migration `b41e7c9d2f60`, applied to Neon 2026-09-30) |
| Application tracking | **Implemented** |
| Operating cost constraint | $0/month, no payment method required ([ADR-004](docs/decisions/ADR-004-technology-stack.md#zero-cost--no-payment-constraint)) |
| Current user education state | High-school senior (expected to become an undergraduate after graduation) |
| Product implementation | Private single-user app with automated discovery (local and hosted) |
| Profile source ingestion | **Implemented and deployed** ([ADR-011](docs/decisions/ADR-011-profile-source-ingestion-and-review.md), migration `c5a1e0f3d7b2`, applied to Neon 2026-10-01) |
| Provider enrichment and source coverage | **Implemented, deployed, activated** (Milestone 7, released 2026-10-04, 20 production ATS boards; [ADR-013](docs/decisions/ADR-013-provider-enrichment-and-source-authority.md); no migration). ATS > feed authority with fallback, network-free ATS discovery from the feed, bulk add of suggested boards, Source Coverage on the Sources page, ATS-first sync ordering |

### Selected stack

| Layer | Selection | Implemented locally? | Provisioned? |
|---|---|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS, Zod, react-router | Yes (`frontend/`) | — |
| Frontend hosting | Vercel Hobby | — | **Yes** (project `internship-finder`, `internship-finder-pi.vercel.app`) |
| Backend | Python 3.12+, FastAPI, Pydantic, pwdlib (Argon2id), httpx2 (ingestion HTTP) | Yes (`backend/`) | — |
| Backend hosting | Render Free Web Service | — | **Yes** (`internship-finder-api`, Oregon, connected to Neon, auto-deploy off) |
| Database | Neon PostgreSQL Free (SQLAlchemy 2.x, Alembic, psycopg) | Yes (6 migrations; local PostgreSQL 18 via `compose.yaml`; tested on ephemeral PostgreSQL 18) | Yes (Neon Free, migrated to `c5a1e0f3d7b2`, owner created, 1,055 opportunities) |
| CI | GitHub Actions (included free usage) | Yes (`.github/workflows/ci.yml`: frontend, backend, e2e jobs; PR/push only; no scheduled jobs) | Running on GitHub |
| End-to-end | Playwright (Chromium) | Yes (`frontend/e2e/`) | — |

## Completed Capabilities

- Engineering documentation framework and ADR-001 through ADR-005.
- Milestone 0: Development Foundation ([PR #2](https://github.com/dude297/internship-finder/pull/2)).
- Milestone 1: Core Domain, Persistence, and Eligibility v1 ([PR #4](https://github.com/dude297/internship-finder/pull/4)).
- Milestone 2: Private Single-User Workflow MVP ([PR #5](https://github.com/dude297/internship-finder/pull/5)): single-user auth, sessions, CSRF, private profile and opportunity API/UI, structured requirements, automatic eligibility evaluation, application tracking, Playwright, local PostgreSQL.
- Milestone 3: Automated Opportunity Discovery and Ingestion ([PR #6](https://github.com/dude297/internship-finder/pull/6)).
- Milestone 3.5: Hosted Deployment Foundation ([PR #7](https://github.com/dude297/internship-finder/pull/7)).
- Milestone 4: Profile Intelligence + Fit Ranking v1 ([PR #9](https://github.com/dude297/internship-finder/pull/9)).
- Milestone 5: Private Profile Source Ingestion + Review ([PR #11](https://github.com/dude297/internship-finder/pull/11)).

## Milestone 3 (complete; merged via PR #6)

Implemented:

- ADR-008 (ingestion and deduplication); ADR-002 remains the governing principle
- migration `726372d627b8`, including the automatic repair of development databases migrated with the pre-merge `7d7f4f8b9a3c` (restores `ck_profiles_graduation_after_status_as_of`; asymmetric downgrade, documented)
- broad discovery feed (zshah101 public JSON API, built in as "Tech Internship Discovery Feed")
- Greenhouse Job Board adapter; Lever Postings adapter (global and EU)
- source registry (safe configuration only; URLs built from hard-coded hosts)
- safe HTTP client (allowlisted HTTPS hosts, public-address check, timeouts, bounded redirects/retries/body size, conditional requests)
- source/run provenance: run history with counts, bounded safe per-item errors, per-record active/closed state and source dates
- conservative cross-source dedup (exact deterministic identifiers only; identity conflicts recorded, never merged, including on the same-source update path)
- one running sync per source, enforced by the partial unique index `uq_ingestion_runs_one_running_per_source`
- source closure only after complete successful snapshots; reactivation
- manual-curation protection (`manually_curated_at`)
- fingerprinted automatic evaluation (no duplicate history on unchanged syncs or title-only edits)
- paginated opportunity list with search and filters
- Sources UI (sync now, sync all, enable/disable, add Greenhouse/Lever by link, latest run)
- discovery UI (imported/manual/closed labels, source names, posted/found dates, provenance on detail, Review requirements action)
- manual sync via UI, API, and CLI (`sync-sources`, `sync-source`)
- synthetic ingestion Playwright workflow (network-free)

Not implemented (by design for this milestone):

- scheduled/cloud sync (the database is local)
- résumé ingestion or profile parsing
- AI
- automatic requirement extraction from posting text
- fit scoring and ranking
- hosted deployment

Validation (2026-09-28, local, after the PR #6 review fixes): backend 358 tests (167 unit + 191 PostgreSQL), frontend 46 Vitest tests, Playwright 2 scenarios, ruff/format/pyright/ESLint/Prettier/tsc/build clean, migration round trip and stale-`7d7f4f8b9a3c` repair, `alembic check`. Live smoke against the real discovery feed on a disposable database: first sync 1,034 created in ~22 s; second sync `no_change` (HTTP 304); forced re-process 1,034 unchanged. GitHub Actions status is recorded in the PR.

## In Progress

Milestone 7.1 (volunteer opportunities) released 2026-10-04 ([deployment.md](docs/deployment.md#milestone-71-release-2026-10-04)): `volunteer` type (migration `f2a7c9d4e1b3`), the `opportunity_type` list filter and **Type** filter, Volunteer label/option; type never affects eligibility or fit. Automated volunteer sources: research only ([docs/research/volunteer-sources-2027.md](docs/research/volunteer-sources-2027.md)). Milestone 8 research, [PR #18](https://github.com/dude297/internship-finder/pull/18). Small debt fixes, [PR #20](https://github.com/dude297/internship-finder/pull/20).

## Milestone 7 (complete; released 2026-10-04 via PR #17)

Release and activation record: [deployment.md](docs/deployment.md#milestone-7-release-2026-10-04). Production after activation: 1,313 open opportunities, 294 with a description (22.4%, from 0.0%), 294 ATS-backed, 1,019 feed-only, 200 still enrichable, 819 unsupported; 20 ATS boards (13 Greenhouse, 2 Lever, 5 Ashby) plus the feed; 4 pending suggestions (none accepted or rejected, 0 canonical requirements, eligibility unchanged); scheduled sync 24.6 s with 21 sources.

Milestone 7 review ([ADR-013](docs/decisions/ADR-013-provider-enrichment-and-source-authority.md)), on `feature/m7-provider-enrichment`. No schema change.

- **Source authority:** canonical fields are owned by the highest-authority active automated record (direct ATS > discovery feed; ties by earliest `first_seen_at`, then ID), derived on every decision from stored `source_type`, so sync order never flips ownership. An ATS board added later takes over a feed-only posting and supplies its description; when the board closes while the feed still lists it, the feed falls back from its stored payload and the posting stays open; the board's return takes over again. Curated opportunities are never rewritten. The opportunity row is locked before ownership is decided, so concurrent syncs serialize.
- **ATS discovery:** derived on read from active feed records (zero network calls) through the feed adapter's `provider_identity`: Greenhouse by exact feed ID; Lever and Ashby by exact feed ID plus an official posting link whose path agrees. Workday/other are counted only.
- **Bulk add:** `POST /api/sources/discovery/add` (owner, CSRF), 1–25 selections by `kind`/`identifier`/`region` only, re-derived from current suggestions, all-or-nothing, `internships_only`, never syncs; a concurrent duplicate returns `409`.
- **Source Coverage:** `GET /api/sources/discovery` and `python -m app.cli source-coverage` (SQL aggregation, 3 queries, no raw payload): description coverage %, ATS-backed, feed-only, enrichable, unsupported, provider distribution, suggestions. Shown on the Sources page and reloaded after every sync.
- **Scheduler:** direct ATS sources sync before the feed; one failing source doesn't stop the others.
- **Requirements:** a takeover that changes the description runs the existing `refresh_candidates()`; candidates stay pending and eligibility is unchanged until owner review.
- **Validation (2026-10-04, local):** backend ruff/format/pyright clean, 992 tests at `b1dd456` plus focused suites after later fixes (identity/discovery 60, authority/ingestion 68, stress 6); frontend lint/format/typecheck/109 Vitest/build; Playwright 10/10 twice on one reused database. Two independent hostile reviews found no BLOCKER/HIGH; the one MEDIUM (trailing newline accepted by `$`-anchored identity patterns) is fixed. Performance: [operations.md](docs/operations.md#operational-source-cap) (recommended cap 50 ATS sources).
- **Production:** still Milestone 6. Activation follows the [Milestone 7 runbook](docs/operations.md#milestone-7-production-activation-runbook-prepared-not-executed) after merge.

## Milestone 4 (complete; merged via PR #9)

Profile Intelligence + Fit Ranking v1 ([ADR-010](docs/decisions/ADR-010-fit-scoring-v1.md), [scoring.md](docs/scoring.md)).

Implemented:

- migration `b41e7c9d2f60`: `profiles` fit preferences; nullable fit columns on `opportunity_evaluations` (all set or all NULL); `ingestion_sources.scope` (existing sources backfilled `all`; the built-in feed must be `all`); `ingestion_runs.filtered_count`
- Match Profile (`GET`/`PUT /api/profile/match`): manual, user-verified `profile_facts` (skills, courses, projects, research, activities, experience) plus interests, preferred locations, remote preference, availability; one atomic save that replaces only its own facts and runs one catalog pass
- deterministic fit scoring v1 (six components, weights 35/20/15/10/10/10, half-up integer rounding, missing = 0 with `coverage`, lexical matcher with a small alias table), breakdown stored per evaluation
- eligibility + fit on every new evaluation; fingerprint-based skipping for both; batched catalog pass (keyset batches of 200)
- `sort=recommended` (eligibility bucket, then fit, then posted/first seen/ID), fit summary on list items, full breakdown on detail
- internships-only title filter for Greenhouse/Lever (default), All postings override, filtered counts, validator reset on scope change (closes/reopens through normal closure)
- UI: Eligibility/Match Profile tabs, Match Profile editor, fit badges with coverage, Recommended/Newest sort, "Why this match?", board scope controls and Filtered counts
- `backend/scripts/perf_smoke.py`

Validation (2026-09-29, local): backend 537 tests (286 unit + 251 PostgreSQL), frontend 63 Vitest tests, Playwright 4 scenarios passing twice on the same reused database, ruff/format/pyright/ESLint/Prettier/tsc/build clean, `git diff --check` clean, migration base → head → `92a17353e5a8` → head → base → head with `alembic check`. Performance (1,100 synthetic): first Match Profile save 2.14 s, unchanged 0.30 s, changed 2.25 s, recommended page 0.05 s ([operations.md](docs/operations.md#evaluation-history-and-re-evaluation-implemented-not-scheduled)). Live smoke on a disposable database (discovery feed): 1,050 created in 20.3 s, Match Profile save 1.34 s, second sync `no_change`. GitHub Actions status is recorded in the PR.

Not implemented (by design): résumé upload/parsing, OCR, AI or embeddings, background jobs or queues, scheduled sync, notifications.

Release (2026-09-29/2026-09-30): PR #9 merged (2026-09-29); production main is `ca9b91b`. Neon migrated to `b41e7c9d2f60` (verified by read-only query 2026-09-30, existing boards backfilled scope `all`, pre-Milestone-4 evaluations kept NULL fit). Render `internship-finder-api` (`srv-dastve60tbcc7392dfgg`) deployed `ca9b91b` (live, finished 2026-09-29 06:21 UTC, auto-deploy off). Vercel production redeployed from `main` via CLI (2026-09-29 07:39 UTC), aliased to `internship-finder-pi.vercel.app`; `/api/health` returned `200` through Vercel on 2026-09-30.

Hosted smoke (2026-09-29, owner-run, all PASS): Match Profile GET; first Match Profile save evaluated 1,055/unchanged 0 in 6,359 ms; identical save evaluated 0/unchanged 1,055 in 1,995 ms; changed save evaluated 1,055/unchanged 0 in 6,391 ms; Recommended page size 100 in 306 ms, page size 50 in 216 ms; all 1,055 opportunities loaded; eligibility-first/fit ordering PASS; all 1,055 scored with scoring version `v1`; coverage present (values `[100]`); "Why This Match" full breakdown PASS; built-in source remains scope `all`; latest run exposes `filtered_count`. Details and full production verification: [deployment.md](docs/deployment.md#production-verification).

All 1,055 current evaluations are `needs_verification` (imported requirements are unassessed), fit range 2–22. Cross-bucket dominance (an eligible/lower-fit opportunity ranking below an ineligible/higher-fit one) is covered by deterministic backend/E2E tests, not by production data. The hosted Match Profile is still the synthetic one used for the smoke; the owner will replace it with the real Match Profile through the app (clearing it first would only add another 1,055 evaluation rows, so it is left in place deliberately).

## Milestone 3.5 (complete; merged via PR #7)

Hosted Deployment Foundation. Runbook and verification results: [docs/deployment.md](docs/deployment.md).

Done:

- ADR-009; migration `92a17353e5a8` (running-run index reconciliation); proxy-aware login throttle (shared `proxy` and `direct` buckets of 10, 50 global per 15 min); Argon2 concurrency guard; `DATABASE_URL` normalization; `HOSTED` mode; `no-store` on `/api`; no slash redirects; cold-start UX; `frontend/vercel.json`
- Neon migrated to `92a17353e5a8`; owner created by the owner with the CLI (`getpass`)
- Render configured (`DATABASE_URL`, `SESSION_COOKIE_SECURE`, `SESSION_TTL_HOURS`, `PYTHON_VERSION`, `HOSTED`, `PROXY_SHARED_SECRET`) and deployed from the feature branch (branch switched temporarily; auto-deploy off)
- Vercel production deployed by CLI from a clean checkout; `PROXY_SHARED_SECRET` is Production-only and Sensitive; Git deployments disabled; Standard Deployment Protection on non-production URLs
- Hosted checks passed: health, same-origin `/api`, API 404s (not the SPA), no slash redirect, SPA deep links, docs hidden, `no-store`, direct-path shared throttle bucket (forged `X-Forwarded-For` ignored), proxy secret accepted, non-production URLs SSO-protected, cold start (~3 min wake; Vercel `502` meanwhile, which the UI shows as waking)

Verified with the owner's login (2026-09-29): cookie attributes (host-only, `HttpOnly; Secure; SameSite=lax; Path=/`), CSRF (`403` without/with a wrong token, `200` with the valid one), first hosted sync (`success`, 1,055 created, 30.8 s) and second sync (`no_change`, 0.8 s), profile re-evaluation over 1,055 opportunities (9–10 s, synthetic profile), invalid source links rejected.

Also verified: session survives Render redeploys and a cold start; the proxied throttle returns `429` on the 11th forged-address failure (after `36b9896`).

Open:

- one Greenhouse/Lever board (optional; none chosen)
- the hosted profile is **synthetic** (location "SYNTHETIC TEST PROFILE - replace"): replace it with the real one when ready (its 2,110 evaluation rows stay as history)

Release (2026-09-29): PR #7 rebase-merged as `d78b93d` (post-merge CI green). Render's branch was switched back to `main` (auto-deploy still off) and `d78b93d` deployed; Vercel production was redeployed from a clean checkout of `d78b93d`. Smoke: health `200` through Vercel, login page loads, database reachable, catalog 1,055, owner and synthetic profile present. The rebase rewrote the branch SHAs cited above: `36b9896` → `03e86c7`, `65964c6` → `17e5877`, `3563021` → `680c2b7`.

## Known Bugs

None open. Fixed during hosted validation (2026-09-29):

- **Per-client login-throttle key was forgeable through Vercel** (fixed in `36b9896`, deployed and verified). Vercel doesn't consistently overwrite a client-supplied `X-Forwarded-For` on the external rewrite, so the leftmost entry is sometimes attacker-controlled. Proxied logins now share one bucket ([ADR-009 §6 amendment](docs/decisions/ADR-009-hosted-deployment-architecture.md#6-login-rate-limiting-behind-the-proxy), [deployment.md](docs/deployment.md#production-verification)).
- Board links with credentials or a port were accepted (reduced to the board name, never fetched). Fixed in `65964c6`, deployed.

## Known Technical Debt

- The login throttle is in memory in one process ([ADR-009 §6](docs/decisions/ADR-009-hosted-deployment-architecture.md#6-login-rate-limiting-behind-the-proxy)): a deploy or restart resets it, and it needs shared state if the backend ever runs more than one worker or instance. All logins through the site share one bucket, so anyone's 10 failed attempts block new logins for up to 15 minutes (accepted; no trustworthy per-browser address exists behind Vercel's rewrite).
- Catalog re-evaluation (profile or Match Profile save) is synchronous in the request. Milestone 4 batches it and skips unchanged pairs (~2 s for 1,100 opportunities locally when everything changes; hosted, measured 2026-09-29 against 1,055 real opportunities: 6.36 s scoring everything, 2.0 s when nothing changed — see [operations.md](docs/operations.md#evaluation-history-and-re-evaluation-implemented-not-scheduled)). A much larger catalog would need background re-evaluation.
- Fit v1 is lexical: synonyms outside the alias table don't match, and a skill that's also a common word (e.g. `Go`) can match unrelated text. Location matching is plain text. Activities and experience don't score ([scoring.md](docs/scoring.md#known-limitations-v1)).
- All 1,055 current evaluations are `needs_verification` (imported requirements are unassessed); fit scores range 2–22. Cross-bucket dominance is exercised by deterministic tests, not by current production data.
- Source sync runs inside the HTTP request (the first discovery-feed sync takes ~20 s locally) behind Vercel's external-rewrite timeout. A timed-out proxy request may still have committed; refresh before retrying.
- Render Free cold starts take about 1–3 minutes (measured 73 s and ~3 min); Vercel either holds the request or returns `502`, which the UI shows as the waking state. Sessions survive the restart.
- No database backups beyond Neon Free's short restore window.
- Board scope is title-based: internships titled without intern/co-op/apprentice words are filtered, and titles such as "Internship Program Manager" are kept. Greenhouse postings are typed by title from Milestone 6 (still `other` in production until released). Boards added before Milestone 4 were migrated to **All postings**.
- A recurring `partial` run (for example, a persistent identity conflict) blocks closure for that source until resolved.
- Deleting an imported opportunity deletes its source records, so the next sync re-imports it (no "hide" yet). There's no "revert to source" for curated opportunities.
- Title/organization search uses `ILIKE '%term%'` without a trigram index; fine at thousands of rows.
- Every opportunity update replaces every requirement row (new IDs; old rule results keep their text with `requirement_id` NULL).
- Expired sessions are deleted only when that user logs in again; there's no periodic cleanup.
- `profiles` is logically a singleton, but only the service enforces that.
- Backend dependencies are range-pinned in `pyproject.toml` without a lock file, so backend installs aren't fully reproducible. The frontend has `package-lock.json`.
- Nothing re-evaluates when the eligibility rules version changes or when time passes an expected graduation/enrollment date.
- `work_authorization` requirements are stored but not evaluated (always `needs_verification`, ELIG-REQ-001).
- Milestone 7: a database error while applying an ADR-013 §5 fallback fails that source's whole run (the stored item already normalized once, so unlikely); a Greenhouse board-host link with an explicit port or trailing dot doesn't trigger the conflicting-board check (the feed ID alone is Greenhouse identity); the abandoned-run threshold (15 min) is shorter than the scheduled workflow timeout (20 min), so keep enabled ATS sources at or under the measured cap of 50; `USERNAME_PATTERN` uses a `$` anchor (accepts a trailing newline; CLI-only owner creation).
- Milestone 6: the requirement extractor favors precision and misses requirements phrased unusually; a deduplicated opportunity whose earliest source has no description (the discovery feed) gets no description and therefore no suggestions from a later board record (resolved by Milestone 7's ATS authority, once released); the scheduled workflow installs range-pinned backend dependencies (no lockfile); nothing alerts when the schedule is auto-disabled after 60 days of repository inactivity (Source Health turns `stale`).

## Architecture Constraints

- Eligibility and fit are separate ([ADR-001](docs/decisions/ADR-001-separate-eligibility-and-fit.md)).
- All sources flow through a shared ingestion pipeline ([ADR-002](docs/decisions/ADR-002-shared-ingestion-pipeline.md), implemented by [ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md)).
- AI is enrichment only, not source of truth, and optional ([ADR-003](docs/decisions/ADR-003-ai-as-enrichment.md)).
- React/Vite static frontend + Python/FastAPI backend + PostgreSQL. $0/month, no payment method. Any required paid dependency needs a new ADR ([ADR-004](docs/decisions/ADR-004-technology-stack.md)).
- Time-aware eligibility, provenance-aware profile facts, layered sources, and external repos as references only ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)).
- Single-user, self-contained authentication; same-origin API; one server-side authorization boundary ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md)).
- Ingestion: adapters never touch the database; exact-identity dedup only; failed/partial runs never close postings; owner-curated content is never overwritten; outbound HTTP only to allowlisted provider hosts ([ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md)).

## Database State

Current (2026-10-04, after the Milestone 7.1 release): migration `f2a7c9d4e1b3`; 1,409 opportunities (1,313 open, 294 with a description); 1,496 source records; 21 ingestion sources (20 ATS + the feed); 6,796 evaluations, every latest `needs_verification`; 0 canonical requirements; 4 pending candidates; 0 applications; 29 MB. Older snapshots below.

Neon Free (project `sweet-dew-33937746`, PostgreSQL 18, `aws-us-west-2`, database `internship_finder`) is migrated to `c5a1e0f3d7b2` (2026-10-01, `alembic check` clean), holds the owner account, and holds 1,055 opportunities. Final counts after the Milestone 5 smoke (2026-10-01, aggregates only): 1,055 opportunities and source records; 6,330 evaluations (4,220 with fit); 1,055 latest evaluations, all with fit and scoring version `v1`; 0 profile sources; 0 profile source artifacts; 10 profile facts (all manual, all `accepted`); 1 profile; 1 owner; 1 ingestion source; 2 runs; 23 MB. Schema head: migration `c5a1e0f3d7b2` (Milestone 5: `profile_source_artifacts`; `profile_sources` upload metadata; `profile_facts.review_state`) on top of `b41e7c9d2f60` (Milestone 4: `profiles` fit preferences; nullable fit columns on `opportunity_evaluations`; `ingestion_sources.scope`; `ingestion_runs.filtered_count`; additive only, no new tables) on top of `92a17353e5a8` (Milestone 3.5 reconciliation of `uq_ingestion_runs_one_running_per_source`), the immutable `726372d627b8` (15 tables), `7d7f4f8b9a3c`, and `3b9c6b57bb60` ([data-model.md](docs/data-model.md)). Verified on disposable PostgreSQL 18 (local Docker; CI on the PR): upgrade, `alembic check`, downgrade through every revision to base, upgrade again, and the stale-`7d7f4f8b9a3c` repair.

Final Neon counts (read-only, 2026-09-30): 1,055 opportunities; 1,055 source records; 4,220 evaluations (2,110 with fit); 1,055 current (latest per opportunity) evaluations, all with a non-null fit score and scoring version `v1`; 1 ingestion source (scope `all`); 2 ingestion runs (both 2026-09-29 00:37 UTC — no sync happened during the release smoke); 1 profile; 0 profile sources; 10 profile facts; 1 owner account; database size 18 MB. Evaluation arithmetic: 2,110 pre-smoke (0 with fit) + 1,055 first Match Profile save + 0 unchanged save + 1,055 changed save = 4,220 total, 2,110 with fit — matches exactly.

Local development uses the Compose database (private data in the `pgdata` volume); `alembic upgrade head` there applies `726372d627b8`, `92a17353e5a8`, `b41e7c9d2f60`, and `c5a1e0f3d7b2`, repairing the graduation constraint and the running-run index if needed.

## Current Scoring Version

`v1`, in production since the Milestone 4 release (2026-09-29): [docs/scoring.md](docs/scoring.md), [ADR-010](docs/decisions/ADR-010-fit-scoring-v1.md).

## Current Eligibility Rules Version

`v1`, implemented 2026-09-25 ([docs/eligibility.md](docs/eligibility.md)). Unchanged by Milestones 2 and 3 (only when evaluations run changed).

## Milestone 6 (complete; merged via PR #13)

Decision record: [ADR-012](docs/decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md); ADR-009 amended (scheduled sync); ADR-011 amended (M5.1 candidate identity). Base: `main` at `d47a799`.

- **M5.1:** the flaky manual-opportunity frontend test waited for "any h1" and could catch the form's own heading (reproduced 38/150 locally; 0/150 after waiting for the named heading). Imported résumé facts are keyed by a stable digest of the original parsed candidate (`resume.<24 hex>`), so a reparse never re-proposes a fact the owner accepted (edited or not) or rejected; legacy `resume.NNN` rows keep the old by-value rule.
- **Requirement suggestions:** pure extractor `requirements-rules` v1 (minimum age, education, U.S. citizenship, work authorization, security clearance; precision over recall, negation/hedge/list guards). Suggestions in `opportunity_requirement_candidates`, identified by a semantic key; generated for new and materially changed imported postings, manual creates/edits, on demand, and by `python -m app.cli scan-requirements`. Never read by eligibility.
- **Review:** `GET/POST /api/opportunities/{id}/requirement-review` (+ `/refresh`): one atomic batch of accept / edit+accept / reject plus an optional explicit assessment status; at most one evaluation of that opportunity; no catalog pass. `complete` only by explicit owner assertion. Requirement Review panel on the opportunity page; list filters for pending suggestions / changed postings / assessment status.
- **Staleness:** a material source change (title, description, deadline, start date; whitespace-insensitive) of a reviewed posting sets "Posting changed since requirement review", downgrades `complete`, keeps accepted requirements, refreshes suggestions, and re-evaluates. Only the earliest active source record rewrites a deduplicated opportunity's canonical fields (previously any source could, which flip-flopped text between sources).
- **Scheduled sync:** `.github/workflows/sync-production.yml`, 06:17/18:17 America/Los_Angeles + manual dispatch, `production` environment secret `PRODUCTION_DATABASE_URL` (not created), refuses an unmigrated schema, actions pinned to SHAs. Inactive until the release configures the secret.
- **Source health:** derived `never_run / healthy / warning / stale / failing / disabled`, consecutive failures, last-success age; shown on Sources.
- **Ashby:** public Job Postings API only (`api.ashbyhq.com`), board name or `jobs.ashbyhq.com` link, listed postings only, internships-only by default.
- **Type classification:** one shared rule (structured intern field, else the title matcher) for every adapter; Greenhouse postings can now be `internship`. The first sync after release reports matching postings as `updated` once.
- **Deadlines:** `deadline_within` 7/14/30, `has_deadline`, `sort=deadline` (upcoming, unknown, passed), client-supplied `today`; "Closing soon" / "Deadline passed" badges.
- **Validation (local, 2026-10-02):** backend ruff, format, pyright clean; 480 unit + 420 PostgreSQL tests; migration base → head → `alembic check` → M5 → M6 → base → head; frontend lint, format, typecheck, 102 Vitest, build; Playwright on one fresh disposable database, four runs in a row: 9/9, then a Playwright worker crash (Windows exit 0xC0000409, no assertion failure), then 9/9 and 9/9. An earlier session saw the same kind of local crash once; it never reproduced as a test failure. Performance (1,100 synthetic opportunities): cold scan 13.3 s / 1,357 statements, rerun 0.95 s / 37; needs-review list page 5 statements for 5 or 50 items; one review batch 0.12 s, one evaluation.
- **Adversarial review:** a separate reviewer found 4 high (form edit unlinking accepted suggestions, duplicate requirements, source flip-flop staleness, extractor contradictions), 4 medium, 8 low; all high and medium items fixed or documented (see the PR). Accepted: backend dependencies aren't hash-locked in the scheduled workflow (no lockfile exists).
- **Final review fixes (2026-10-02):** (1) review ownership: a review only deletes or replaces *suggestion-owned* requirements (`deterministic_parser` + `requirements-rules`), and only when no other accepted suggestion still links them; manual rows are never mutated or deleted by a review; an accepted edit relinks (or creates) instead of rewriting; the `complete` downgrade happens only when a reject actually deletes a requirement; a form `PUT` keeps the provenance of requirements resubmitted unchanged. (2) Ashby `isListed` is strictly boolean and required: `false` is excluded (closes on a complete run), missing/non-boolean is an item error (partial run, nothing closes). Revalidated: 487 unit + 435 PostgreSQL, 102 Vitest, Playwright 9/9, migration round-trip, flake stress.
- **Release (2026-10-02):** [PR #13](https://github.com/dude297/internship-finder/pull/13) rebase-merged at the approved head `ff47970`; `main` `80257c5` (post-merge CI `37066645594` green); Neon migrated `c5a1e0f3d7b2` → `e6d1a4b8c2f9`; Render deploy `dep-db03iknavr4c73e10b8g`; Vercel production `dpl_8kqCpb15vP5q1rcJpsSB3Pvt6XJk`; scheduled sync configured; production requirement scan run. Record: [deployment.md](docs/deployment.md#milestone-6-release-2026-10-02).
- **Production results:** first scheduled-sync dispatch green (feed: 1,117 fetched, 138 created, 102 updated, 877 unchanged, 76 closed, 0 invalid; all 76 closures verified absent from the live feed); Source Health `healthy`. Requirement scan: 1,193 scanned, 1,050 refreshed, 143 unchanged, 0 failed, **0 suggestions** in 92.9 s, because the only production source (the discovery feed) carries no posting descriptions (0 of 1,193 opportunities have one). Requirements, evaluations, assessment statuses, and eligibility unchanged by the scan. No Ashby source added.

## Milestone 5 (complete; merged via PR #11)

Private Profile Source Ingestion + Review ([ADR-011](docs/decisions/ADR-011-profile-source-ingestion-and-review.md)). Released 2026-10-01; release record in [deployment.md](docs/deployment.md#milestone-5-release-2026-10-01).

Implemented:

- migration `c5a1e0f3d7b2`: `profile_source_artifacts` (original bytes, BYTEA, 1:1, cascade); `profile_sources` upload metadata (`content_type`, `byte_size`, `parser_name`, `parser_version`, UNIQUE `(profile_id, content_sha256)`); `profile_facts.review_state` (pending/accepted/rejected, NOT NULL, database default `accepted` kept so Milestone 4 manual inserts keep working; backfill matches the Milestone 4 fit filter exactly, so no fit input or fingerprint changes on upgrade; CHECK: a non-manual fact is accepted exactly when verified)
- fit reads only accepted facts (`fit_profile_input`)
- deterministic parser `resume-sections` v1: plain text (strict UTF-8) and text-based PDF (pypdf, first 20 pages, 100,000 characters), content sniffing only, section alias table, list and entry sections, dedupe, 200 candidates; PDF text extraction in a spawned child process (15 s limit, 256 MB address space on Linux), and at most one such child per application process at a time (a process-local lock; a second concurrent PDF upload or re-parse gets `503` with `Retry-After: 5` instead of queueing, since the per-child memory ceiling alone doesn't protect a 512 MB Render Free host from two children at once)
- private API `/api/profile/sources`: list, upload (2 MB, Content-Length checked before form parsing, one file part only, 409 duplicate / 411 / 413 / 415 / 422 / 503), detail, download (attachment, `nosniff`, `no-store`), review batch (accept / edit + accept / reject; at most one catalog pass, only when an accepted fit fact changed), re-parse (replaces only pending facts; never resurrects decided ones; 503 if a PDF is already being extracted), delete (artifact and facts by cascade; Match Profile facts untouched; one pass if it had accepted fit facts)
- upload and re-parse skip candidates already accepted anywhere in the profile
- UI: **Imported Profile** tab (upload, source list with parser/version and counts, grouped review with staged changes and one Apply, rescoring message, download, re-parse, delete)
- dependencies `pypdf>=6.19,<7` (BSD-3-Clause) and `python-multipart>=0.0.32,<0.1` (Apache-2.0), both above every published advisory

Validation (2026-09-30, local): backend 702 tests (368 unit + 334 PostgreSQL), frontend 74 Vitest tests, Playwright 6 tests (all specs) passing twice on the same reused database, ruff/format/pyright/ESLint/Prettier/tsc/build clean, migration base → head, `alembic check`, head → `b41e7c9d2f60` → head. Performance (1,100 synthetic, machine under parallel load): a 44-fact review batch runs one catalog pass, 1,100 evaluated, 32 SQL statements, 3.5 s (the Match Profile save measured 3.3–3.7 s in the same run). Security review: a 0.2 MB flate-bomb PDF reached 2.6 GB in-process; fixed by the isolated extraction (now rejected at the time limit, or by the memory limit on Linux, with the event loop still serving requests). Follow-up fix: two concurrent PDF extractions could still OOM the 512 MB Render Free host even with the per-child memory cap, so extraction is now limited to one child per application process at a time (`503`/`Retry-After: 5` on a second concurrent PDF upload or re-parse) — see ADR-011 §2. Linux container smoke (python:3.12-slim, 1 GB): while a flate-bomb PDF was extracting, `/api/health` answered `200` in 5 ms, a second PDF got `503` with `Retry-After: 5`, a plain-text upload got `201`, and the peak was 1 extraction child; the hostile PDF ended `422` at 4.5 s (memory limit), leaving 0 children, and a later normal PDF got `201` in 0.66 s. A final adversarial review of the gate found only two LOW issues (pipe left open on a failed spawn; a garbled child reply surfaced as `500`), both fixed with tests. Backward compatibility: `profile_facts.review_state` has the database default `accepted`, so the Milestone 4 app (whose manual Match Profile inserts don't name it) keeps working on the migrated schema; the CHECK still rejects an unverified non-manual fact that omits it, and Milestone 5 code always sets it explicitly. Covered by migration tests (M4-style insert at head, rejected unverified parser insert, fit input identical before and after the migration) and reviewed independently (no blocker/high/medium).

Release (2026-10-01): PR #11 rebase-merged at the approved head `12bb4cc` (CI `36771548316`); resulting `main` `639e447`, post-merge CI `36811148911` green (backend, frontend, e2e). Neon read-only baseline matched (`b41e7c9d2f60`; 1,055 opportunities; 4,220 evaluations, 2,110 with fit; 0 profile sources; 10 facts), then `alembic upgrade head` → `c5a1e0f3d7b2`, `alembic check` clean: 10/10 facts `accepted`, `review_state` NOT NULL with default `'accepted'`, both review CHECKs present, 0 sources/artifacts, evaluations unchanged (no rescore). The Milestone 4 app stayed healthy on the migrated schema (health, session lookup, profile API) until Render deployed `639e447` (`dep-dautc2gjo6nc73ehekag`); Vercel production `dpl_8jfYs2Ychc77wiH7JbWCMjroEwUF` from a clean checkout of `639e447`. Hosted smoke with synthetic files only, all checks passed ([deployment.md](docs/deployment.md#milestone-5-release-2026-10-01)). Evaluation history: 4,220 before; +1,055 on accept (one pass); +1,055 on deleting the source with accepted fit facts; 6,330 after (append-only by design). The stray Render service `internship-finder` was deleted.

Known limitations and debt:

- Headings outside the alias table and the stop list (e.g. "Certifications") don't end the previous section, so their lines join it; unusual layouts parse poorly. The owner reviews everything before it counts.
- Each PDF upload starts a Python process (~0.5–1 s). A hostile PDF can use up to 15 s and the child's memory limit; the memory limit is Linux-only (local Windows development has only the time limit). Only one such child runs per process at a time; a second concurrent PDF upload or re-parse gets `503` (`Retry-After: 5`) rather than queueing. Adequate only for the current one-worker, one-instance Render deployment (ADR-009).
- Deleted artifacts leave PostgreSQL pages until autovacuum (logical, not immediate, erasure).
- DOCX, OCR, transcripts, course lists, and AI enrichment aren't supported.
- Accepted imported facts appear on Imported Profile, not in the Match Profile editor; both feed fit.
- Duplicate suppression is by (category, name). Accepting a fact under an edited name means a later re-parse proposes the original parsed name again as a new **pending** fact (seen in the hosted smoke). Pending facts never score; the owner rejects it once.

## Active Opportunity Sources

- Tech Internship Discovery Feed (zshah101 public JSON API) — built in, manual sync.
- Greenhouse boards, Lever sites, and Ashby boards — 20 in production since 2026-10-04 (suggested from the feed, Internships only; [docs/sources.md](docs/sources.md#production-boards-2026-10-04)). Synced twice daily with the feed.
- Manual entry.
- Excluded: `SuryaHarikrishnan/2027-internship-tracker` listing data (licensing unclear).

Details, licensing basis, and attribution: [docs/sources.md](docs/sources.md).

## Environment / Deployment Notes

- Backend variables: `DATABASE_URL` (required except for `/api/health`), `SESSION_TTL_HOURS`, `SESSION_COOKIE_SECURE`, hosted-only `HOSTED` and `PROXY_SHARED_SECRET`, and the test-only `INGESTION_FIXTURE_FILE` (never set for real use). The frontend has no build-time variables; Vercel Production holds `PROXY_SHARED_SECRET` for the `/api` rewrite. See [docs/development.md](docs/development.md#environment-variables).
- Hosting (ADR-009): Vercel Hobby `internship-finder` → Render Free `internship-finder-api` (Oregon) → Neon Free. Deploys are manual: migrate → Render → Vercel ([docs/deployment.md](docs/deployment.md)). The owner confirmed the Vercel plan (Hobby, no payment method) on 2026-09-28.
- Each provisioning step must confirm that no payment method is required before creating the account or project.

## Deferred Work

- Deployment workflows (deploys stay manual).
- Early-college/research-program sources (layer 3). Ashby and scheduled sync are implemented in Milestone 6.

## Next Planned Task

Review the Milestone 8 research ([PR #18](https://github.com/dude297/internship-finder/pull/18)) and the small debt PR ([#20](https://github.com/dude297/internship-finder/pull/20)); then Milestone 8 Tier 1 under a new ADR-014 (SmartRecruiters adapter + curated program registry).

Previously: Review the Milestone 7 PR (`feature/m7-provider-enrichment` → `main`). After approval: merge, deploy (Render, then Vercel; no migration), then follow the [Milestone 7 activation runbook](docs/operations.md#milestone-7-production-activation-runbook-prepared-not-executed): a bounded first batch of suggested boards, manual syncs, coverage before/after, every suggestion left pending.

Previously: review the Milestone 6 PR. After approval, follow its release runbook (merge → migrate Neon → deploy Render and Vercel → hosted smoke → configure the `production` environment and secret → one manual sync dispatch → verify health → candidate scan only with explicit approval). Separately, the owner replaces the hosted synthetic Match Profile with the real one through the app.

## Recent Important Decisions

- 2026-10-04: Milestone 7.1 released. PR #19 → `main` `0a636e2`; Neon migrated to `f2a7c9d4e1b3`; Render `dep-db1c2oc9v7es73eshpd0`, Vercel `dpl_AZuVPW533BkqzuzRwozvx12J5PEG`; synthetic volunteer smoke 13/13, cleaned.
- 2026-10-04: Milestone 7 released. PR #17 rebase-merged at approved head `64ce84d`; `main` `bc23629` (post-merge CI green). Render `dep-db1bksjncjis73c2apr0`, Vercel `dpl_Gj9D5tdBYQENGrMavySfoa3xFS57`. 20 ATS boards activated in two batches; coverage 0.0% → 22.4%.
- 2026-10-03: ADR-013 accepted (on the Milestone 7 branch): automated-source authority (ATS > feed, earliest then ID), takeover and fallback from stored payloads, network-free ATS discovery from exact feed identities, owner-only bulk add of suggestions (max 25, never syncs), Source Coverage, ATS-first scheduled ordering. No migration.
- 2026-10-02: ADR-012 accepted (on the Milestone 6 branch): deterministic requirement suggestions with owner review, semantic identity, explicit-only completeness, source-change staleness, a GitHub Actions scheduled sync against Neon (ADR-009 amended), derived source health, Ashby public boards, shared type classification, and deadline discovery. ADR-011 amended for the M5.1 candidate identity.
- 2026-10-01: Milestone 5 released. PR #11 rebase-merged at approved head `12bb4cc`; production `main` is `639e447` (post-merge CI green). Neon migrated `b41e7c9d2f60` → `c5a1e0f3d7b2`; Render and Vercel production redeployed from `639e447`; hosted synthetic TXT and PDF smoke passed; stray Render service `internship-finder` (`srv-dasrvgt9fdbs73eqlmi0`) deleted. Details: Milestone 5 section above and [deployment.md](docs/deployment.md#milestone-5-release-2026-10-01).
- 2026-09-29/2026-09-30: Milestone 4 released. PR #9 merged (2026-09-29); production `main` is `ca9b91b`. Neon migrated to `b41e7c9d2f60`; Render and Vercel production redeployed from `main`; hosted smoke passed (see the Milestone 4 section above and [deployment.md](docs/deployment.md#production-verification)).
- 2026-09-29: ADR-010 accepted: fit scoring v1 (deterministic, weights 35/20/15/10/10/10, missing evidence scores 0 with coverage, one canonical config), eligibility-first ranking, Match Profile on `profile_facts` + `profiles` preference columns, fit fingerprints, a synchronous batched catalog pass (no queue), and an internships-only title scope for Greenhouse/Lever boards (default; validators cleared on scope change). Migration `b41e7c9d2f60`.

- 2026-09-28: ADR-009 accepted: Vercel same-origin `/api` rewrite → Render (one instance, one worker) → Neon direct endpoint; proxy-secret-gated login throttle (amended 2026-09-29 to shared `proxy`/`direct` buckets of 10 after Vercel was found to pass forged forwarding headers; 50 global); Argon2 concurrency 2; `HOSTED` mode; manual migrations and deploys; Git deployments off on Vercel; `PROXY_SHARED_SECRET` Production-only; no scheduler or keep-alive. Migration `92a17353e5a8` reconciles the running-run index.
- 2026-09-28: PR #6 review fixes: the same-source/external-ID update path is subject to the identity-conflict rule (the record's own unchanged URL is exempt for rule-4 false duplicates); one running ingestion run per source is enforced by the partial unique index `uq_ingestion_runs_one_running_per_source` (added to `726372d627b8` before merge). Milestone 3 merged via PR #6.
- 2026-09-27: ADR-008 accepted: source registry with safe configuration only; adapters without database access; one shared pipeline with per-item savepoints and run history; closure only after complete successful snapshots; exact deterministic identifiers for cross-source dedup (no fuzzy matching; conflicts recorded, never merged); manual-curation protection; fingerprinted automatic evaluation; allowlisted HTTPS-only network access via `httpx2`; zshah101 feed consumed through its API only; SuryaHarikrishnan listing data excluded; no scheduler while the database is local.
- 2026-09-27: Migration `726372d627b8` repairs the pre-merge `7d7f4f8b9a3c` graduation constraint automatically (asymmetric downgrade). The manual-patch instruction was removed from the docs.
- 2026-09-27: `GET /api/opportunities` is paginated (`limit` ≤ 100) and filtered server-side; the default view is open postings plus manual opportunities.
- 2026-09-27: PR #5 review fixes: stale-session-check guard, confirmed-only logout, and the education timeline invariant `expected_graduation_date > education_status_as_of` (API `422` + `ck_profiles_graduation_after_status_as_of`). Eligibility rules stay `v1`.
- 2026-09-27: ADR-007 accepted: single-user username/password auth (Argon2id via pwdlib), CLI-only owner bootstrap, opaque DB sessions (SHA-256 stored), HttpOnly `SameSite=Lax` cookie (`Secure` by default), HMAC-derived CSRF token, one `require_owner` boundary, same-origin `/api`, in-memory login throttle with production blocked pending review.
- 2026-09-27: Milestone 2 re-evaluation: opportunity mutations evaluate; eligibility-relevant profile changes re-evaluate all opportunities synchronously in the same transaction.
- 2026-09-27: Application tracking is one `applications` row per opportunity with statuses saved/applying/applied/interview/offer/accepted/rejected/withdrawn and no enforced transitions.
- 2026-09-26: PR #4 review fixes: evaluation-level `depends_on_projected_status`; `requirements_assessment_status` and ELIG-REQ-000; `latest_evaluation` breaks ties by `id`. Milestone 1 merged; ADR-006 accepted.
- 2026-09-25: ADR-006 core domain persistence model. PostgreSQL tests use a disposable database; SQLite is not used.
- 2026-09-25: Repository made public. Public-repository privacy and secret-handling rules added. New commits use the GitHub noreply address.
- 2026-09-25: Milestone 0 scaffold (ESLint instead of oxlint, `httpx2` test client, Python 3.12 floor, tests ignore `backend/.env`).
- 2026-09-24: ADR-004 accepted (React/Vite, Python/FastAPI, Neon, Vercel Hobby, Render Free, GitHub Actions; $0/no-payment constraint).
- 2026-09-24: ADR-005 accepted (time-aware eligibility, provenance-aware profile ingestion, layered sources, open-source reuse policy).
- 2026-09-24: ADR-001, ADR-002, ADR-003 accepted.
