# Project State

> `PROJECT_STATE.md` must be updated after every meaningful implementation milestone or architecture change.

Last Updated: 2026-09-27
Current Milestone: **Milestone 3 — Automated Opportunity Discovery and Ingestion**, implemented on `feature/opportunity-ingestion`; **awaiting review** (not merged). Milestone 2 complete ([PR #5](https://github.com/dude297/internship-finder/pull/5)). Milestone 1 complete ([PR #4](https://github.com/dude297/internship-finder/pull/4)). Milestone 0 complete ([PR #2](https://github.com/dude297/internship-finder/pull/2)).
Current Production Version: None (not deployed)
Active Development Branch: `feature/opportunity-ingestion`. Remote: https://github.com/dude297/internship-finder

## Repository Visibility

| | |
|---|---|
| Repository visibility | **Public** (set on GitHub 2026-09-25) |
| Public repository safety | **Active** ([CLAUDE.md](CLAUDE.md#public-repository-safety), [ENGINEERING_GUIDELINES.md §16](ENGINEERING_GUIDELINES.md#16-public-repository-security-and-privacy)) |
| Private user data in Git | **Prohibited** |

Real résumé, transcript, profile, and application documents stay outside the repository, in the database or gitignored local storage. The owner's real profile is entered only through the running app. Downloaded source payloads are never committed; tests use fabricated provider fixtures.

## Current Objective

Review and merge Milestone 3. Do not start Milestone 4 before that.

## Status Summary

Terms: **Selected** = decided in an ADR. **Scaffolded/Implemented** = code exists in the repository and is tested. **Provisioned** = account/project/resource actually created. **Deployed** = running in a hosted environment.

| Area | Status |
|---|---|
| Technology stack | **Selected** ([ADR-004](docs/decisions/ADR-004-technology-stack.md)). Runs locally. Not provisioned. |
| Source/profile strategy | **Selected** ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)). Opportunity ingestion implemented (ADR-008). No profile parsers. |
| Core domain persistence | **Implemented** ([ADR-006](docs/decisions/ADR-006-core-domain-persistence-model.md), migration `3b9c6b57bb60`, immutable) |
| Authentication / private API | **Implemented, local only** ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md), migration `7d7f4f8b9a3c`, immutable). Not Internet-production-ready (see Known Technical Debt) |
| Opportunity ingestion | **Implemented, local, manual sync only** ([ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md), migration `726372d627b8`) — in review |
| Eligibility | **Implemented** v1 (rules version `v1`), evaluated automatically (only when inputs change) |
| Application tracking | **Implemented** |
| Operating cost constraint | $0/month, no payment method required ([ADR-004](docs/decisions/ADR-004-technology-stack.md#zero-cost--no-payment-constraint)) |
| Current user education state | High-school senior (expected to become an undergraduate after graduation) |
| Product implementation | Private single-user app with automated discovery (local) |
| Next milestone | Milestone 4 (proposed, not started) |

### Selected stack

| Layer | Selection | Implemented locally? | Provisioned? |
|---|---|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS, Zod, react-router | Yes (`frontend/`) | — |
| Frontend hosting | Vercel Hobby | — | No |
| Backend | Python 3.12+, FastAPI, Pydantic, pwdlib (Argon2id), httpx2 (ingestion HTTP) | Yes (`backend/`) | — |
| Backend hosting | Render Free Web Service | — | No |
| Database | Neon PostgreSQL Free (SQLAlchemy 2.x, Alembic, psycopg) | Yes (3 migrations; local PostgreSQL 18 via `compose.yaml`; tested on ephemeral PostgreSQL 18) | No |
| CI | GitHub Actions (included free usage) | Yes (`.github/workflows/ci.yml`: frontend, backend, e2e jobs; PR/push only; no scheduled jobs) | Running on GitHub |
| End-to-end | Playwright (Chromium) | Yes (`frontend/e2e/`) | — |

## Completed Capabilities

- Engineering documentation framework and ADR-001 through ADR-005.
- Milestone 0: Development Foundation ([PR #2](https://github.com/dude297/internship-finder/pull/2)).
- Milestone 1: Core Domain, Persistence, and Eligibility v1 ([PR #4](https://github.com/dude297/internship-finder/pull/4)).
- Milestone 2: Private Single-User Workflow MVP ([PR #5](https://github.com/dude297/internship-finder/pull/5)): single-user auth, sessions, CSRF, private profile and opportunity API/UI, structured requirements, automatic eligibility evaluation, application tracking, Playwright, local PostgreSQL.

## Milestone 3 (implemented on `feature/opportunity-ingestion`, awaiting review)

Implemented:

- ADR-008 (ingestion and deduplication); ADR-002 remains the governing principle
- migration `726372d627b8`, including the automatic repair of development databases migrated with the pre-merge `7d7f4f8b9a3c` (restores `ck_profiles_graduation_after_status_as_of`; asymmetric downgrade, documented)
- broad discovery feed (zshah101 public JSON API, built in as "Tech Internship Discovery Feed")
- Greenhouse Job Board adapter; Lever Postings adapter (global and EU)
- source registry (safe configuration only; URLs built from hard-coded hosts)
- safe HTTP client (allowlisted HTTPS hosts, public-address check, timeouts, bounded redirects/retries/body size, conditional requests)
- source/run provenance: run history with counts, bounded safe per-item errors, per-record active/closed state and source dates
- conservative cross-source dedup (exact deterministic identifiers only; identity conflicts recorded, never merged)
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

Milestone 3 PR review. Next exact task after merge: update this file to "Milestone 3 complete" with the merge commit and post-merge CI run, then plan Milestone 4.

## Known Bugs

None known.

## Known Technical Debt

- **Production deployment is blocked until login rate limiting is reviewed.** The failed-login throttle is in memory, per process, per client IP, and resets on restart ([ADR-007 §8](docs/decisions/ADR-007-single-user-auth-and-private-api.md#8-login-throttling)). The same-origin hosting topology and `Secure` cookies also need review before deployment ([deployment.md](docs/deployment.md#blockers-before-any-hosted-deployment)).
- Profile re-evaluation is synchronous and re-evaluates every opportunity (~4 s for ~1,100 opportunities locally). Needs batching or background work before hosted use or a much larger catalog ([operations.md](docs/operations.md)).
- Source sync runs inside the HTTP request (the first discovery-feed sync takes ~20 s). Fine locally; a hosted deployment with request timeouts would need a background job.
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

Selected: Neon PostgreSQL. Not provisioned. Schema head: migration `726372d627b8` (15 tables) on top of the immutable `7d7f4f8b9a3c` and `3b9c6b57bb60` ([data-model.md](docs/data-model.md)). Verified on disposable PostgreSQL 18 (local Docker; CI on the PR): upgrade, `alembic check`, downgrade through every revision to base, upgrade again, and the stale-`7d7f4f8b9a3c` repair. Local development uses the Compose database (private data in the `pgdata` volume); `alembic upgrade head` there applies `726372d627b8` and repairs the graduation constraint if needed.

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

- Backend variables: `DATABASE_URL` (required except for `/api/health`), `SESSION_TTL_HOURS`, `SESSION_COOKIE_SECURE`, and the test-only `INGESTION_FIXTURE_FILE` (never set for real use). The frontend has none. See [docs/development.md](docs/development.md#environment-variables).
- Hosting is selected (Vercel Hobby, Render Free, Neon Free) but not provisioned. Deployment blockers are listed in [docs/deployment.md](docs/deployment.md#blockers-before-any-hosted-deployment).
- Each provisioning step must confirm that no payment method is required before creating the account or project.

## Deferred Work

- Provisioning Vercel, Render, and Neon, and the same-origin hosted topology review.
- Scheduled source sync (needs a hosted database) and deployment workflows.
- Ashby and early-college/research-program sources (layer 3).

## Next Planned Task

Review Milestone 3 (PR from `feature/opportunity-ingestion`). After merge: record the merge and post-merge CI here, then plan Milestone 4 (proposed: profile enrichment and fit scoring). Not started.

## Recent Important Decisions

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
