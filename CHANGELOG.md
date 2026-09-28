# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

- Milestone 3.5: hosted deployment foundation ([ADR-009](docs/decisions/ADR-009-hosted-deployment-architecture.md), runbook in [docs/deployment.md](docs/deployment.md)).
  - Migration `92a17353e5a8`: creates `uq_ingestion_runs_one_running_per_source` on databases migrated with the pre-merge `726372d627b8`; no-op on fresh databases; refuses (with a clear error) if duplicate `running` rows exist; the downgrade keeps the index.
  - Topology: Vercel Hobby (static build, same-origin `/api` rewrite) → Render Free (FastAPI, one instance, one worker) → Neon Free (PostgreSQL 18, direct endpoint). Manual migrations and deploys; no scheduler or keep-alive.
  - Login throttling: 10 failures per client key and 50 in total per sliding 15 minutes, checked before password work. Only requests carrying the Vercel proxy secret (`X-IF-Proxy-Secret`, from `PROXY_SHARED_SECRET`) are keyed by `X-Forwarded-For`; direct callers share one bucket.
  - Argon2 hash/verify limited to 2 concurrent operations (parameters and dummy verification unchanged).
  - `HOSTED=true`: no `/docs`, `/redoc`, `/openapi.json`; requires `SESSION_COOKIE_SECURE=true`.
  - `Cache-Control: no-store` on `/api`; `redirect_slashes=False`.
  - `DATABASE_URL` accepts Neon's `postgresql://` URL (driver scheme switched, rest untouched) for runtime, CLI, and Alembic.
  - Frontend: an unreachable backend (network error, 5xx, non-JSON wake-up page) shows "server waking up" with bounded retries and a Retry button instead of logging out.
  - `frontend/vercel.json`; Python 3.12 and Node 24.x pinned for hosting and CI.

- Milestone 3: automated opportunity discovery and ingestion ([ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md)).
  - Migration `726372d627b8`: `ingestion_sources` (with the built-in "Tech Internship Discovery Feed"), `ingestion_runs`, `ingestion_run_errors`, `opportunity_identifiers`; `opportunities.posted_at` and `manually_curated_at`; source-record lifecycle (`ingestion_source_id`, `is_active`, `closed_at`, source dates, `content_hash`); `opportunity_evaluations.input_fingerprint`.
  - Automatic repair of development databases migrated with the pre-merge `7d7f4f8b9a3c` (restores `ck_profiles_graduation_after_status_as_of`; no manual SQL).
  - Shared ingestion pipeline: typed normalized adapter output, per-item savepoints, run history with counts and bounded safe errors, partial-success semantics, closure only after complete successful snapshots, reactivation, and conditional requests (ETag / Last-Modified → `no_change`).
  - Adapters: zshah101 discovery feed (public JSON API), Greenhouse Job Board API, Lever Postings API (global and EU). Source HTML is converted to plain text.
  - Safe HTTP client (`httpx2`, now a runtime dependency): allowlisted HTTPS hosts, public-address check, timeouts, bounded redirects/retries/size, `Retry-After`.
  - Conservative deduplication through deterministic identifiers (feed ID, Greenhouse/Lever provider IDs, exact canonical URL); identity conflicts are recorded, never merged.
  - Manual-curation protection: owner edits survive later syncs.
  - Sources API (`/api/sources`: list, add from board links, rename/enable, sync one, sync all, run history) and CLI (`sync-sources`, `sync-source`).
  - Paginated opportunity list (`limit` ≤ 100) with search and availability/source/eligibility/application/work-mode filters, freshest first.
  - Frontend: Sources page, filters and pagination, imported/manual/closed labels, Source provenance and a Review requirements action on the detail page.
  - Tests: ingestion unit and PostgreSQL tests with synthetic provider fixtures, Sources API and CLI tests, migration reconciliation tests, Vitest for the new pages, and a network-free Playwright ingestion workflow.

- Milestone 2: private single-user workflow MVP ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md)).
  - Owner authentication: Argon2id (`pwdlib[argon2]`), CLI-only account creation and password rotation (`python -m app.cli create-owner` / `set-password`), opaque server-side sessions (SHA-256 stored), HttpOnly `SameSite=Lax` cookie (`Secure` by default), HMAC-derived CSRF token on every unsafe private request, one `require_owner` boundary, generic login failures, and an in-memory failed-login throttle.
  - Migration `7d7f4f8b9a3c`: `auth_users`, `auth_sessions`, `applications`, and the `profiles` CHECK `ck_profiles_graduation_after_status_as_of`.
  - Education timeline invariant: `expected_graduation_date` must be after `education_status_as_of` when both are set (`422` from the API, CHECK constraint in PostgreSQL). Eligibility rules stay `v1`.
  - Auth reliability: a stale initial session check can't overwrite a newer login (auth generation guard), and logout keeps the user signed in with a visible error unless the server confirms it (`204`/`401`).
  - Private API: `/api/auth/*`, `GET/PUT /api/profile`, opportunity CRUD with a complete-set requirements array, `POST /api/opportunities/{id}/evaluate`, and `PUT/DELETE /api/opportunities/{id}/application`. Consistent error model (no SQL, stack traces, or echoed passwords).
  - Automatic eligibility evaluation on opportunity changes, and re-evaluation of all opportunities when an eligibility-relevant profile field changes (same transaction, history appended).
  - Manual opportunities keep provenance (`manual` source record, no fabricated external ID).
  - Application tracking (saved → withdrawn, submitted date, private notes).
  - Frontend: react-router app shell, login, profile editor, opportunity list/detail/form, structured requirement editor, plain-language eligibility explanations, projected-status notice, application tracker.
  - Playwright end-to-end workflow (Chromium) and a CI `e2e` job.
  - `compose.yaml` for a local-only PostgreSQL 18.

- Milestone 1: core domain, persistence, and eligibility v1 ([ADR-006](docs/decisions/ADR-006-core-domain-persistence-model.md)).
  - Initial Alembic migration `3b9c6b57bb60` with `profiles`, `profile_sources`, `profile_facts`, `opportunities`, `opportunity_source_records`, `opportunity_requirements`, `opportunity_evaluations`, and `eligibility_rule_results`.
  - Temporal education resolver (`app/profile/education.py`).
  - Eligibility rules v1 (ELIG-REQ-000, ELIG-AGE-001, ELIG-EDU-001, ELIG-CIT-001, ELIG-REQ-001) with the composite `evaluate_eligibility` and persistent evaluation history.
  - `opportunities.requirements_assessment_status` (`unassessed` default / `partial` / `complete`). Unassessed or partial requirement sets are at least `needs_verification` (ELIG-REQ-000), so an empty requirement list means `eligible` only when the assessment is complete.
  - CI runs migrations (upgrade, drift check, downgrade, upgrade) and integration tests against an ephemeral PostgreSQL 18 container.
- Added public-repository privacy and secret-handling safeguards.
- Milestone 0 development foundation: a React/TypeScript/Vite/Tailwind frontend (`frontend/`) that shows backend health, validated with Zod, and a FastAPI backend (`backend/`) with `GET /api/health`, a SQLAlchemy base, and an empty Alembic environment. Includes ESLint/Prettier/Vitest and Ruff/Pyright/Pytest tooling, plus a GitHub Actions CI workflow.
- Initial engineering documentation framework.
- Repository operating rules (`CLAUDE.md`, `ENGINEERING_GUIDELINES.md`).
- Project-state handoff document (`PROJECT_STATE.md`).
- Architecture decision records (ADR-001, ADR-002, ADR-003).
- ADR-004: technology stack (React/Vite/Tailwind frontend on Vercel Hobby, Python/FastAPI backend on Render Free, Neon PostgreSQL, GitHub Actions) under a $0/month, no-payment-method constraint.
- ADR-005: layered opportunity sources, time-aware eligibility, provenance-aware profile ingestion, and open-source reuse policy.

### Changed

- `GET /api/opportunities` returns a page (`{items, total, limit, offset}`) instead of an array, and each summary includes origin, availability, source names, and posted/first-seen dates.
- Automatic evaluation (opportunity create/update, sync) appends a new evaluation only when the eligibility inputs changed. `POST /api/opportunities/{id}/evaluate` still always appends. This resolves the Milestone 2 debt "updates always append an evaluation, even when only the title changed".
- The frontend calls relative `/api` URLs through a Vite proxy (same-origin). `VITE_API_BASE_URL`, the backend's `FRONTEND_ORIGIN`, and the CORS middleware were removed.
- The health-only home page was replaced by the authenticated app.

- Topic docs, `ENGINEERING_GUIDELINES.md`, `README.md`, and `PROJECT_STATE.md` updated for ADR-004/ADR-005. The planned eligibility rule ELIG-EDU-001 is now time-aware.
