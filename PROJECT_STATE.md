# Project State

> `PROJECT_STATE.md` must be updated after every meaningful implementation milestone or architecture change.

Last Updated: 2026-09-28
Current Milestone: **Milestone 3.5 — Hosted Deployment Foundation** (implemented; deployed from the review branch; hosted checks mostly done; one open security bug in the login throttle key; see In Progress and Known Bugs). Milestone 3 — Automated Opportunity Discovery and Ingestion complete; merged via [PR #6](https://github.com/dude297/internship-finder/pull/6). Milestone 2 complete ([PR #5](https://github.com/dude297/internship-finder/pull/5)). Milestone 1 complete ([PR #4](https://github.com/dude297/internship-finder/pull/4)). Milestone 0 complete ([PR #2](https://github.com/dude297/internship-finder/pull/2)).
Current Production Version: `feature/hosted-deployment-foundation` (unmerged, deployed for validation) on https://internship-finder-pi.vercel.app
Active Development Branch: `feature/hosted-deployment-foundation`. Remote: https://github.com/dude297/internship-finder

## Repository Visibility

| | |
|---|---|
| Repository visibility | **Public** (set on GitHub 2026-09-25) |
| Public repository safety | **Active** ([CLAUDE.md](CLAUDE.md#public-repository-safety), [ENGINEERING_GUIDELINES.md §16](ENGINEERING_GUIDELINES.md#16-public-repository-security-and-privacy)) |
| Private user data in Git | **Prohibited** |

Real résumé, transcript, profile, and application documents stay outside the repository, in the database or gitignored local storage. The owner's real profile is entered only through the running app. Downloaded source payloads are never committed; tests use fabricated provider fixtures.

## Current Objective

Milestone 3.5 — Hosted Deployment Foundation.

## Status Summary

Terms: **Selected** = decided in an ADR. **Scaffolded/Implemented** = code exists in the repository and is tested. **Provisioned** = account/project/resource actually created. **Deployed** = running in a hosted environment.

| Area | Status |
|---|---|
| Technology stack | **Selected** ([ADR-004](docs/decisions/ADR-004-technology-stack.md)); hosting per [ADR-009](docs/decisions/ADR-009-hosted-deployment-architecture.md). **Provisioned and deployed** (Vercel Hobby → Render Free → Neon Free) from the review branch. |
| Source/profile strategy | **Selected** ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)). Opportunity ingestion implemented (ADR-008). No profile parsers. |
| Core domain persistence | **Implemented** ([ADR-006](docs/decisions/ADR-006-core-domain-persistence-model.md), migration `3b9c6b57bb60`, immutable) |
| Authentication / private API | **Implemented and hosted** ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md), migration `7d7f4f8b9a3c`, immutable; hardened by [ADR-009](docs/decisions/ADR-009-hosted-deployment-architecture.md) §6–§7) |
| Opportunity ingestion | **Implemented, manual sync only** ([ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md), migration `726372d627b8`) |
| Eligibility | **Implemented** v1 (rules version `v1`), evaluated automatically (only when inputs change) |
| Application tracking | **Implemented** |
| Operating cost constraint | $0/month, no payment method required ([ADR-004](docs/decisions/ADR-004-technology-stack.md#zero-cost--no-payment-constraint)) |
| Current user education state | High-school senior (expected to become an undergraduate after graduation) |
| Product implementation | Private single-user app with automated discovery (local) |
| Next milestone | Milestone 3.5 — Hosted Deployment Foundation (current); then Milestone 4 (proposed, not started) |

### Selected stack

| Layer | Selection | Implemented locally? | Provisioned? |
|---|---|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS, Zod, react-router | Yes (`frontend/`) | — |
| Frontend hosting | Vercel Hobby | — | **Yes** (project `internship-finder`, `internship-finder-pi.vercel.app`) |
| Backend | Python 3.12+, FastAPI, Pydantic, pwdlib (Argon2id), httpx2 (ingestion HTTP) | Yes (`backend/`) | — |
| Backend hosting | Render Free Web Service | — | **Yes** (`internship-finder-api`, Oregon, connected to Neon, auto-deploy off) |
| Database | Neon PostgreSQL Free (SQLAlchemy 2.x, Alembic, psycopg) | Yes (4 migrations; local PostgreSQL 18 via `compose.yaml`; tested on ephemeral PostgreSQL 18) | Yes (Neon Free, migrated to `92a17353e5a8`, owner created, catalog empty) |
| CI | GitHub Actions (included free usage) | Yes (`.github/workflows/ci.yml`: frontend, backend, e2e jobs; PR/push only; no scheduled jobs) | Running on GitHub |
| End-to-end | Playwright (Chromium) | Yes (`frontend/e2e/`) | — |

## Completed Capabilities

- Engineering documentation framework and ADR-001 through ADR-005.
- Milestone 0: Development Foundation ([PR #2](https://github.com/dude297/internship-finder/pull/2)).
- Milestone 1: Core Domain, Persistence, and Eligibility v1 ([PR #4](https://github.com/dude297/internship-finder/pull/4)).
- Milestone 2: Private Single-User Workflow MVP ([PR #5](https://github.com/dude297/internship-finder/pull/5)): single-user auth, sessions, CSRF, private profile and opportunity API/UI, structured requirements, automatic eligibility evaluation, application tracking, Playwright, local PostgreSQL.
- Milestone 3: Automated Opportunity Discovery and Ingestion ([PR #6](https://github.com/dude297/internship-finder/pull/6)).

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

Milestone 3.5 — Hosted Deployment Foundation, on `feature/hosted-deployment-foundation` (PR open, not merged). Runbook and verification results: [docs/deployment.md](docs/deployment.md).

Done:

- ADR-009; migration `92a17353e5a8` (running-run index reconciliation); proxy-aware login throttle (10 per client, 50 global per 15 min); Argon2 concurrency guard; `DATABASE_URL` normalization; `HOSTED` mode; `no-store` on `/api`; no slash redirects; cold-start UX; `frontend/vercel.json`
- Neon migrated to `92a17353e5a8`; owner created by the owner with the CLI (`getpass`)
- Render configured (`DATABASE_URL`, `SESSION_COOKIE_SECURE`, `SESSION_TTL_HOURS`, `PYTHON_VERSION`, `HOSTED`, `PROXY_SHARED_SECRET`) and deployed from the feature branch (branch switched temporarily; auto-deploy off)
- Vercel production deployed by CLI from a clean checkout; `PROXY_SHARED_SECRET` is Production-only and Sensitive; Git deployments disabled; Standard Deployment Protection on non-production URLs
- Hosted checks passed: health, same-origin `/api`, API 404s (not the SPA), no slash redirect, SPA deep links, docs hidden, `no-store`, direct-path shared throttle bucket (forged `X-Forwarded-For` ignored), proxy secret accepted, non-production URLs SSO-protected, cold start (~3 min wake; Vercel `502` meanwhile, which the UI shows as waking)

Verified with the owner's login (2026-09-29): cookie attributes (host-only, `HttpOnly; Secure; SameSite=lax; Path=/`), CSRF (`403` without/with a wrong token, `200` with the valid one), first hosted sync (`success`, 1,055 created, 30.8 s) and second sync (`no_change`, 0.8 s), profile re-evaluation over 1,055 opportunities (9–10 s, synthetic profile), invalid source links rejected.

Open:

- the per-client throttle key bug ([Known Bugs](#known-bugs)): needs a diagnostic deploy and a fix
- deploy `65964c6` (board-link fix) to Render; session survival across that redeploy
- session return after a cold start
- one Greenhouse/Lever board (optional; none chosen)
- the hosted profile is **synthetic** (location "SYNTHETIC TEST PROFILE - replace"): replace it with the real one when ready (its 2,110 evaluation rows stay as history)

After merge: switch Render's branch back to `main`, deploy `main`, and redeploy Vercel production from `main` ([deployment.md](docs/deployment.md#unmerged-branch-validation)).

## Known Bugs

- **Per-client login-throttle key is forgeable through Vercel** (found 2026-09-29, open). Vercel doesn't consistently overwrite a client-supplied `X-Forwarded-For` on the external rewrite, so the leftmost entry is sometimes attacker-controlled. The global 50-per-15-minutes cap and the direct-path shared bucket still bound guessing. Details and fix options: [deployment.md](docs/deployment.md#production-verification).
- Board links with credentials or a port were accepted (reduced to the board name, never fetched). Fixed in `65964c6`; not yet deployed to Render.

## Known Technical Debt

- The login throttle is in memory in one process ([ADR-009 §6](docs/decisions/ADR-009-hosted-deployment-architecture.md#6-login-rate-limiting-behind-the-proxy)): a deploy or restart resets it, and it needs shared state if the backend ever runs more than one worker or instance. The global cap lets a distributed attacker lock the owner out for up to 15 minutes (accepted).
- Profile re-evaluation is synchronous and re-evaluates every opportunity (~4 s for ~1,100 opportunities locally; ~10 s for 1,055 opportunities hosted). Batching/background work is proposed for Milestone 4 ([operations.md](docs/operations.md)).
- Source sync runs inside the HTTP request (the first discovery-feed sync takes ~20 s locally) behind Vercel's external-rewrite timeout. A timed-out proxy request may still have committed; refresh before retrying.
- Render Free cold starts take about 3 minutes; meanwhile Vercel returns `502` and the UI shows the waking state.
- No database backups beyond Neon Free's short restore window.
- Direct ATS boards import every published posting (not only internships); they're typed `other` unless a structured field says internship.
- A recurring `partial` run (for example, a persistent identity conflict) blocks closure for that source until resolved.
- Deleting an imported opportunity deletes its source records, so the next sync re-imports it (no "hide" yet). There's no "revert to source" for curated opportunities.
- Title/organization search uses `ILIKE '%term%'` without a trigram index; fine at thousands of rows.
- Every opportunity update replaces every requirement row (new IDs; old rule results keep their text with `requirement_id` NULL).
- Expired sessions are deleted only when that user logs in again; there's no periodic cleanup.
- `profiles` is logically a singleton, but only the service enforces that.
- Backend dependencies are range-pinned in `pyproject.toml` without a lock file, so backend installs aren't fully reproducible. The frontend has `package-lock.json`.
- Nothing re-evaluates when the eligibility rules version changes or when time passes an expected graduation/enrollment date.
- `work_authorization` requirements are stored but not evaluated (always `needs_verification`, ELIG-REQ-001).
- Profile preferences, remote preference, and availability aren't modeled yet (they arrive with fit scoring).

## Architecture Constraints

- Eligibility and fit are separate ([ADR-001](docs/decisions/ADR-001-separate-eligibility-and-fit.md)).
- All sources flow through a shared ingestion pipeline ([ADR-002](docs/decisions/ADR-002-shared-ingestion-pipeline.md), implemented by [ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md)).
- AI is enrichment only, not source of truth, and optional ([ADR-003](docs/decisions/ADR-003-ai-as-enrichment.md)).
- React/Vite static frontend + Python/FastAPI backend + PostgreSQL. $0/month, no payment method. Any required paid dependency needs a new ADR ([ADR-004](docs/decisions/ADR-004-technology-stack.md)).
- Time-aware eligibility, provenance-aware profile facts, layered sources, and external repos as references only ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)).
- Single-user, self-contained authentication; same-origin API; one server-side authorization boundary ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md)).
- Ingestion: adapters never touch the database; exact-identity dedup only; failed/partial runs never close postings; owner-curated content is never overwritten; outbound HTTP only to allowlisted provider hosts ([ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md)).

## Database State

Neon Free (project `sweet-dew-33937746`, PostgreSQL 18, `aws-us-west-2`, database `internship_finder`) is migrated to `92a17353e5a8` (`alembic check` clean), holds the owner account, and after the first hosted sync holds 1,055 opportunities (13 MB on 2026-09-29). Schema head: migration `92a17353e5a8` (Milestone 3.5 reconciliation of `uq_ingestion_runs_one_running_per_source`, no new tables) on top of the immutable `726372d627b8` (15 tables), `7d7f4f8b9a3c`, and `3b9c6b57bb60` ([data-model.md](docs/data-model.md)). Verified on disposable PostgreSQL 18 (local Docker; CI on the PR): upgrade, `alembic check`, downgrade through every revision to base, upgrade again, and the stale-`7d7f4f8b9a3c` repair. Local development uses the Compose database (private data in the `pgdata` volume); `alembic upgrade head` there applies `726372d627b8` and `92a17353e5a8`, repairing the graduation constraint and the running-run index if needed.

## Current Scoring Version

Not implemented yet. Planned v1 documented in [docs/scoring.md](docs/scoring.md).

## Current Eligibility Rules Version

`v1`, implemented 2026-09-25 ([docs/eligibility.md](docs/eligibility.md)). Unchanged by Milestones 2 and 3 (only when evaluations run changed).

## Active Opportunity Sources

- Tech Internship Discovery Feed (zshah101 public JSON API) — built in, manual sync.
- Greenhouse boards and Lever sites — added by the owner, manual sync.
- Manual entry.
- Excluded: `SuryaHarikrishnan/2027-internship-tracker` listing data (licensing unclear).

Details, licensing basis, and attribution: [docs/sources.md](docs/sources.md).

## Environment / Deployment Notes

- Backend variables: `DATABASE_URL` (required except for `/api/health`), `SESSION_TTL_HOURS`, `SESSION_COOKIE_SECURE`, hosted-only `HOSTED` and `PROXY_SHARED_SECRET`, and the test-only `INGESTION_FIXTURE_FILE` (never set for real use). The frontend has no build-time variables; Vercel Production holds `PROXY_SHARED_SECRET` for the `/api` rewrite. See [docs/development.md](docs/development.md#environment-variables).
- Hosting (ADR-009): Vercel Hobby `internship-finder` → Render Free `internship-finder-api` (Oregon) → Neon Free. Deploys are manual: migrate → Render → Vercel ([docs/deployment.md](docs/deployment.md)). The owner confirmed the Vercel plan (Hobby, no payment method) on 2026-09-28.
- Each provisioning step must confirm that no payment method is required before creating the account or project.

## Deferred Work

- Scheduled source sync (needs a hosted database) and deployment workflows.
- Ashby and early-college/research-program sources (layer 3).

## Next Planned Task

Fix the forgeable per-client throttle key and deploy `65964c6` ([Known Bugs](#known-bugs)), finish the open hosted checks ([In Progress](#in-progress)), then review and merge the Milestone 3.5 PR and restore Render to `main`. Milestone 4 (proposed: profile enrichment and fit scoring v1, with batched/background profile re-evaluation and an internships-only filter for Greenhouse/Lever) follows. Not started.

## Recent Important Decisions

- 2026-09-28: ADR-009 accepted: Vercel same-origin `/api` rewrite → Render (one instance, one worker) → Neon direct endpoint; proxy-secret-keyed login throttle (10 per client, 50 global); Argon2 concurrency 2; `HOSTED` mode; manual migrations and deploys; Git deployments off on Vercel; `PROXY_SHARED_SECRET` Production-only; no scheduler or keep-alive. Migration `92a17353e5a8` reconciles the running-run index.
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
