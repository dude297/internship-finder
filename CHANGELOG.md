# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

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

- The frontend calls relative `/api` URLs through a Vite proxy (same-origin). `VITE_API_BASE_URL`, the backend's `FRONTEND_ORIGIN`, and the CORS middleware were removed.
- The health-only home page was replaced by the authenticated app.

- Topic docs, `ENGINEERING_GUIDELINES.md`, `README.md`, and `PROJECT_STATE.md` updated for ADR-004/ADR-005. The planned eligibility rule ELIG-EDU-001 is now time-aware.
