# Project State

> `PROJECT_STATE.md` must be updated after every meaningful implementation milestone or architecture change.

Last Updated: 2026-09-27
Current Milestone: **Milestone 2 — Private Single-User Workflow MVP**, complete; merged via [PR #5](https://github.com/dude297/internship-finder/pull/5). Milestone 1 complete ([PR #4](https://github.com/dude297/internship-finder/pull/4)). Milestone 0 complete ([PR #2](https://github.com/dude297/internship-finder/pull/2)).
Current Production Version: None (not deployed)
Active Development Branch: None. Remote: https://github.com/dude297/internship-finder

## Repository Visibility

| | |
|---|---|
| Repository visibility | **Public** (set on GitHub 2026-09-25) |
| Public repository safety | **Active** ([CLAUDE.md](CLAUDE.md#public-repository-safety), [ENGINEERING_GUIDELINES.md §16](ENGINEERING_GUIDELINES.md#16-public-repository-security-and-privacy)) |
| Private user data in Git | **Prohibited** |

Real résumé, transcript, profile, and application documents stay outside the repository, in the database or gitignored local storage. The owner's real profile is entered only through the running app.

## Current Objective

Plan Milestone 3 — opportunity discovery and ingestion.

## Status Summary

Terms: **Selected** = decided in an ADR. **Scaffolded/Implemented** = code exists in the repository and is tested. **Provisioned** = account/project/resource actually created. **Deployed** = running in a hosted environment.

| Area | Status |
|---|---|
| Technology stack | **Selected** ([ADR-004](docs/decisions/ADR-004-technology-stack.md)). Runs locally. Not provisioned. |
| Source/profile strategy | **Selected** ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)). Persistence/provenance schema implemented (ADR-006). No collectors or parsers. |
| Core domain persistence | **Implemented** ([ADR-006](docs/decisions/ADR-006-core-domain-persistence-model.md), migration `3b9c6b57bb60`, immutable) |
| Authentication / private API | **Implemented, local only** ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md), migration `7d7f4f8b9a3c`). Not Internet-production-ready (see Known Technical Debt) |
| Eligibility | **Implemented** v1 (rules version `v1`), evaluated automatically |
| Application tracking | **Implemented** |
| Operating cost constraint | $0/month, no payment method required ([ADR-004](docs/decisions/ADR-004-technology-stack.md#zero-cost--no-payment-constraint)) |
| Current user education state | High-school senior (expected to become an undergraduate after graduation) |
| Product implementation | Private single-user workflow MVP (local) |
| Next milestone | Milestone 3 (proposed, not started): opportunity discovery/ingestion against the private app |

### Selected stack

| Layer | Selection | Implemented locally? | Provisioned? |
|---|---|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS, Zod, react-router | Yes (`frontend/`) | — |
| Frontend hosting | Vercel Hobby | — | No |
| Backend | Python 3.12+, FastAPI, Pydantic, pwdlib (Argon2id) | Yes (`backend/`) | — |
| Backend hosting | Render Free Web Service | — | No |
| Database | Neon PostgreSQL Free (SQLAlchemy 2.x, Alembic, psycopg) | Yes (2 migrations; local PostgreSQL 18 via `compose.yaml`; tested on ephemeral PostgreSQL 18) | No |
| CI | GitHub Actions (included free usage) | Yes (`.github/workflows/ci.yml`: frontend, backend, e2e jobs; PR/push only) | Running on GitHub |
| End-to-end | Playwright (Chromium) | Yes (`frontend/e2e/`) | — |

## Completed Capabilities

- Engineering documentation framework and ADR-001 through ADR-005.
- Milestone 0: Development Foundation ([PR #2](https://github.com/dude297/internship-finder/pull/2)): React/Vite/TypeScript/Tailwind scaffold, FastAPI `GET /api/health`, lint/format/typecheck/test/build tooling, SQLAlchemy/Alembic baseline, CI.
- Milestone 1: Core Domain, Persistence, and Eligibility v1 ([PR #4](https://github.com/dude297/internship-finder/pull/4)): schema `3b9c6b57bb60`, profile and opportunity provenance, structured requirements, temporal education resolver, eligibility v1 (ELIG-REQ-000, ELIG-AGE-001, ELIG-EDU-001, ELIG-CIT-001, ELIG-REQ-001), requirement assessment state, evaluation history, PostgreSQL CI.
- Milestone 2: Private Single-User Workflow MVP ([PR #5](https://github.com/dude297/internship-finder/pull/5)):
  - single-user authentication ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md)): Argon2id, CLI-only owner bootstrap and password rotation, no registration
  - server-side sessions (only the SHA-256 of the token stored) in an HttpOnly, `SameSite=Lax`, `Secure`-by-default cookie
  - CSRF protection (HMAC-derived token, `X-CSRF-Token` on every unsafe private request)
  - one authorization dependency on every private endpoint; same-origin API (Vite proxy), CORS removed
  - private profile API/UI with ISO 3166-1 validation and the education timeline invariant (`expected_graduation_date > education_status_as_of`, API `422` + PostgreSQL CHECK)
  - stale-response-safe auth state (auth generation guard) and confirmed-only logout (network/server failure keeps the user signed in with an error)
  - manual opportunity API/UI with `manual` source provenance
  - structured requirement editing (complete-set replacement) and explicit requirement-assessment state
  - automatic eligibility evaluation on opportunity changes and re-evaluation of every opportunity on eligibility-relevant profile changes (history appended, same transaction)
  - plain-language eligibility explanations and the projected-status notice
  - application tracking (status, submitted date, private notes)
  - Playwright end-to-end workflow in CI
  - local-only PostgreSQL 18 via Docker Compose

## Not Implemented

- Résumé parsing, profile ingestion, and profile-fact editing
- External opportunity sources, collectors, and schedulers
- Fit scoring and ranking
- AI
- Hosted deployment (no Neon, Vercel, or Render provisioning)

## In Progress

Nothing. Milestone 3 has not started.

## Known Bugs

None known.

## Known Technical Debt

- **Production deployment is blocked until login rate limiting is reviewed.** The failed-login throttle is in memory, per process, per client IP, and resets on restart ([ADR-007 §8](docs/decisions/ADR-007-single-user-auth-and-private-api.md#8-login-throttling)). The same-origin hosting topology and `Secure` cookies also need review before deployment ([deployment.md](docs/deployment.md#blockers-before-any-hosted-deployment)).
- Profile re-evaluation is synchronous and re-evaluates every opportunity. Fine for a manual catalog; needs batching or background work at ingestion scale ([operations.md](docs/operations.md#evaluation-history-and-re-evaluation-implemented-not-scheduled)).
- Opportunity updates always append an evaluation, even when only the title changed, and replace every requirement row (new IDs; old rule results keep their text with `requirement_id` NULL).
- Expired sessions are deleted only when that user logs in again; there's no periodic cleanup.
- `profiles` is logically a singleton, but only the service enforces that (it only ever creates one row); the database has no one-row maximum. Non-blocking for the local single-user MVP; review before hosted or concurrent use.
- Backend dependencies are range-pinned in `pyproject.toml` without a lock file, so backend installs aren't fully reproducible. The frontend has `package-lock.json`.
- Nothing re-evaluates when the eligibility rules version changes or when time passes an expected graduation/enrollment date.
- `work_authorization` requirements are stored but not evaluated (always `needs_verification`, ELIG-REQ-001).
- Profile preferences, remote preference, and availability aren't modeled yet (they arrive with fit scoring).

## Architecture Constraints

- Eligibility and fit are separate ([ADR-001](docs/decisions/ADR-001-separate-eligibility-and-fit.md)).
- All sources flow through a shared ingestion pipeline ([ADR-002](docs/decisions/ADR-002-shared-ingestion-pipeline.md)).
- AI is enrichment only, not source of truth, and optional ([ADR-003](docs/decisions/ADR-003-ai-as-enrichment.md)).
- React/Vite static frontend + Python/FastAPI backend + PostgreSQL. $0/month, no payment method. Any required paid dependency needs a new ADR ([ADR-004](docs/decisions/ADR-004-technology-stack.md)).
- Time-aware eligibility, provenance-aware profile facts, layered sources, and external repos as references only ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)).
- Single-user, self-contained authentication; same-origin API; one server-side authorization boundary ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md)).

## Database State

Selected: Neon PostgreSQL. Not provisioned. Schema head: migration `7d7f4f8b9a3c` (11 tables) on top of the immutable Milestone 1 migration `3b9c6b57bb60` ([data-model.md](docs/data-model.md)). Verified on disposable PostgreSQL 18 (local Docker and CI): upgrade, `alembic check`, downgrade to `3b9c6b57bb60` and to base, upgrade again. Local development uses the Compose database (private data in the `pgdata` volume).

## Current Scoring Version

Not implemented yet. Planned v1 documented in [docs/scoring.md](docs/scoring.md).

## Current Eligibility Rules Version

`v1`, implemented 2026-09-25 ([docs/eligibility.md](docs/eligibility.md)). Unchanged by Milestone 2 (only when evaluations run changed).

## Active Opportunity Sources

None (manual entry only, recorded as `manual` source records). Planned sources and research references are listed in [docs/sources.md](docs/sources.md).

## Environment / Deployment Notes

- Backend variables: `DATABASE_URL` (required except for `/api/health`), `SESSION_TTL_HOURS`, `SESSION_COOKIE_SECURE`. The frontend has none. See [docs/development.md](docs/development.md#environment-variables).
- Hosting is selected (Vercel Hobby, Render Free, Neon Free) but not provisioned. Deployment blockers are listed in [docs/deployment.md](docs/deployment.md#blockers-before-any-hosted-deployment).
- Each provisioning step must confirm that no payment method is required before creating the account or project.

## Deferred Work

- Provisioning Vercel, Render, and Neon, and the same-origin hosted topology review.
- Scheduled workflows and deployment workflows: not added.
- License verification for the `zshah101` and `SuryaHarikrishnan` reference repositories: needed before any use beyond reading.

## Next Planned Task

Plan **Milestone 3 — opportunity discovery/ingestion** (first structured sources through the shared ingestion pipeline, feeding the private app). Not started.

## Recent Important Decisions

- 2026-09-27: PR #5 review fixes: (1) `AuthProvider` ignores a session check that resolves after a newer auth transition; (2) logout clears local auth state only on `204`/`401`, otherwise shows "Couldn't log out. You're still signed in."; (3) new invariant `expected_graduation_date > education_status_as_of` (strict, because the transition takes effect on the graduation date), enforced by `ProfileBody` and `ck_profiles_graduation_after_status_as_of`, added to the unmerged Milestone 2 migration `7d7f4f8b9a3c` (Milestone 1 migration untouched). Eligibility rules stay `v1`.
- 2026-09-27: ADR-007 accepted: single-user username/password auth (Argon2id via pwdlib), CLI-only owner bootstrap, opaque DB sessions (SHA-256 stored), HttpOnly `SameSite=Lax` cookie (`Secure` by default), HMAC-derived CSRF token, one `require_owner` boundary, same-origin `/api` (Vite proxy; CORS and `FRONTEND_ORIGIN`/`VITE_API_BASE_URL` removed), in-memory login throttle with production blocked pending review.
- 2026-09-27: Milestone 2 re-evaluation: every opportunity mutation appends an evaluation when a profile exists; a profile change to an eligibility input (the `ProfileInput` fields) re-evaluates all opportunities synchronously in the same transaction. Resolves the Milestone 1 debt "nothing re-evaluates when the profile changes".
- 2026-09-27: Application tracking is one `applications` row per opportunity (single-user) with statuses saved/applying/applied/interview/offer/accepted/rejected/withdrawn and no enforced transitions.
- 2026-09-26: PR #4 review fix: the evaluation-level `depends_on_projected_status` is true only when the overall outcome depends on projected results. Milestone 1 merged; ADR-006 accepted.
- 2026-09-26: PR #4 review fix: `opportunities.requirements_assessment_status` and rule ELIG-REQ-000. `latest_evaluation` breaks `evaluated_at` ties by `id`.
- 2026-09-25: ADR-006 core domain persistence model. Eligibility v1 clarifications (explicit citizenship mismatch is `ineligible`; unevaluable requirements are `needs_verification`). PostgreSQL tests use a disposable database; SQLite is not used.
- 2026-09-25: Repository made public. Public-repository privacy and secret-handling rules added. New commits use the GitHub noreply address.
- 2026-09-25: Milestone 0 scaffold (ESLint instead of oxlint, `httpx2` test client, Python 3.12 floor, tests ignore `backend/.env`).
- 2026-09-24: ADR-004 accepted (React/Vite, Python/FastAPI, Neon, Vercel Hobby, Render Free, GitHub Actions; $0/no-payment constraint).
- 2026-09-24: ADR-005 accepted (time-aware eligibility, provenance-aware profile ingestion, layered sources, open-source reuse policy).
- 2026-09-24: ADR-001, ADR-002, ADR-003 accepted.
