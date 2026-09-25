# Project State

> `PROJECT_STATE.md` must be updated after every meaningful implementation milestone or architecture change.

Last Updated: 2026-09-25
Current Milestone: Milestone 1 — Core Domain, Persistence, and Eligibility v1 (implemented on `feature/core-domain-eligibility`; awaiting review). Milestone 0 complete ([PR #2](https://github.com/dude297/internship-finder/pull/2)).
Current Production Version: None (not deployed)
Active Development Branch: `feature/core-domain-eligibility` (Milestone 1, PR open for review). Remote: https://github.com/dude297/internship-finder

## Repository Visibility

| | |
|---|---|
| Repository visibility | **Public** (set on GitHub 2026-09-25) |
| Public repository safety | **Active** ([CLAUDE.md](CLAUDE.md#public-repository-safety), [ENGINEERING_GUIDELINES.md §16](ENGINEERING_GUIDELINES.md#16-public-repository-security-and-privacy)) |
| Private user data in Git | **Prohibited** |

Real résumé, transcript, profile, and application documents stay outside the repository, in the database or gitignored local storage.

## Current Objective

Review and merge Milestone 1. Milestone 2 is not started.

## Status Summary

Terms: **Selected** = decided in an ADR. **Scaffolded/Implemented** = code exists in the repository and is tested. **Provisioned** = account/project/resource actually created. **Deployed** = running in a hosted environment.

| Area | Status |
|---|---|
| Technology stack | **Selected** ([ADR-004](docs/decisions/ADR-004-technology-stack.md)). Scaffolded locally. Not provisioned. |
| Source/profile strategy | **Selected** ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)). Persistence/provenance schema implemented (ADR-006). No collectors or parsers. |
| Core domain persistence | **Implemented** ([ADR-006](docs/decisions/ADR-006-core-domain-persistence-model.md), migration `3b9c6b57bb60`) |
| Eligibility | **Implemented** v1 (rules version `v1`) |
| Operating cost constraint | $0/month, no payment method required ([ADR-004](docs/decisions/ADR-004-technology-stack.md#zero-cost--no-payment-constraint)) |
| Current user education state | High-school senior (expected to become an undergraduate after graduation) |
| Development foundation | **Implemented** (Milestone 0) |
| Product implementation | Backend domain only (no product API or UI) |
| Next milestone | Milestone 2 (proposed): private profile/manual opportunity API + local application workflow. Not started. |

### Selected stack

| Layer | Selection | Scaffolded locally? | Provisioned? |
|---|---|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS, Zod | Yes (`frontend/`) | — |
| Frontend hosting | Vercel Hobby | — | No |
| Backend | Python 3.12+, FastAPI, Pydantic | Yes (`backend/`) | — |
| Backend hosting | Render Free Web Service | — | No |
| Database | Neon PostgreSQL Free (SQLAlchemy 2.x, Alembic, psycopg) | Yes (models, initial migration; tested on ephemeral PostgreSQL 18) | No |
| CI | GitHub Actions (included free usage) | Yes (`.github/workflows/ci.yml`, PR/push only, ephemeral PostgreSQL service) | Running on GitHub |

## Completed Capabilities

- Engineering documentation framework and ADR-001 through ADR-005.
- Milestone 0: Development Foundation:
  - React/Vite/TypeScript (strict)/Tailwind frontend scaffold
  - FastAPI backend scaffold with `GET /api/health` → `{"status": "ok"}`
  - Local frontend → backend health integration (loading, healthy, and error states), with the API client validated by Zod
  - Frontend unit tests (Vitest + React Testing Library)
  - Backend unit tests (Pytest)
  - Lint, format, typecheck, test, and build commands ([docs/development.md](docs/development.md))
  - SQLAlchemy declarative base and Alembic baseline (no migrations, no tables)
  - GitHub Actions CI workflow (lint, typecheck, test, build)
- Milestone 1: Core Domain, Persistence, and Eligibility v1 (awaiting review):
  - initial domain schema ([data-model.md](docs/data-model.md), [ADR-006](docs/decisions/ADR-006-core-domain-persistence-model.md))
  - initial Alembic migration `3b9c6b57bb60` (upgrade and downgrade verified on PostgreSQL)
  - profile provenance (`profile_sources`, `profile_facts`)
  - opportunity provenance (`opportunity_source_records`)
  - structured requirements (`opportunity_requirements`)
  - temporal education resolver
  - eligibility v1 (ELIG-AGE-001, ELIG-EDU-001, ELIG-CIT-001, ELIG-REQ-001)
  - persistent evaluations with per-rule results (history kept)
  - PostgreSQL CI integration (migration round trip, drift check, integration tests)

## Not Implemented

- Production infrastructure / hosted databases. No Neon provisioning, Vercel deployment, or Render deployment.
- Authentication
- Sensitive profile APIs (deliberately absent until authentication exists)
- Résumé upload/parsing and profile ingestion
- Source collectors and opportunity ingestion
- Fit scoring and ranking
- Frontend opportunity UI (profile editor, opportunity list, eligibility UI, application tracker)
- AI

## In Progress

Milestone 1 PR open for review. Not merged.

## Known Bugs

None known.

## Known Technical Debt

- Backend dependencies are range-pinned in `pyproject.toml` without a lock file, so backend installs aren't fully reproducible. The frontend has `package-lock.json`.
- No Playwright end-to-end tests yet.
- Re-evaluation is a library call only. Nothing re-runs evaluations when the profile, rules version, or reference dates change.
- `work_authorization` requirements are stored but not evaluated (always `needs_verification`, ELIG-REQ-001).
- Profile preferences, remote preference, and availability aren't modeled yet (they arrive with fit scoring).

## Architecture Constraints

- Eligibility and fit are separate ([ADR-001](docs/decisions/ADR-001-separate-eligibility-and-fit.md)).
- All sources flow through a shared ingestion pipeline ([ADR-002](docs/decisions/ADR-002-shared-ingestion-pipeline.md)).
- AI is enrichment only, not source of truth, and optional ([ADR-003](docs/decisions/ADR-003-ai-as-enrichment.md)).
- React/Vite static frontend + Python/FastAPI backend + PostgreSQL. $0/month, no payment method. Any required paid dependency needs a new ADR ([ADR-004](docs/decisions/ADR-004-technology-stack.md)).
- Time-aware eligibility, provenance-aware profile facts, layered sources, and external repos as references only ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)).

## Database State

Selected: Neon PostgreSQL. Not provisioned. Schema head: migration `3b9c6b57bb60` (8 tables, see [data-model.md](docs/data-model.md)). Verified only on disposable PostgreSQL 18 (local Docker and CI).

## Current Scoring Version

Not implemented yet. Planned v1 documented in [docs/scoring.md](docs/scoring.md).

## Current Eligibility Rules Version

`v1`, implemented 2026-09-25 ([docs/eligibility.md](docs/eligibility.md)).

## Active Opportunity Sources

None. Planned sources and research references are listed in [docs/sources.md](docs/sources.md).

## Environment / Deployment Notes

- Local variables: `VITE_API_BASE_URL` (frontend, public), `FRONTEND_ORIGIN` and `DATABASE_URL` (backend, server-only). None are required for local dev. See [docs/development.md](docs/development.md#environment-variables).
- Hosting is selected (Vercel Hobby, Render Free, Neon Free) but not provisioned. See [docs/deployment.md](docs/deployment.md).
- Each provisioning step must confirm that no payment method is required before creating the account or project.

## Deferred Work

- Provisioning Vercel, Render, and Neon: deferred until there is a feature to deploy.
- Scheduled workflows and deployment workflows: not added.
- License verification for the `zshah101` and `SuryaHarikrishnan` reference repositories: needed before any use beyond reading.

## Next Planned Task

Review and merge Milestone 1. Then, proposed: **Milestone 2 — private profile/manual opportunity API + local application workflow** (requires an authentication/API-exposure design first). Not started.

## Recent Important Decisions

- 2026-09-25: ADR-006 core domain persistence model (canonical profile vs facts, structured requirements, separate source records, evaluation history, portable VARCHAR enums and JSON). Eligibility v1 clarifications: explicit citizenship mismatch is `ineligible`; unevaluable requirements are `needs_verification` (ELIG-REQ-001). PostgreSQL tests use a disposable database; SQLite is not used.
- 2026-09-25: Repository made public. Public-repository privacy and secret-handling rules added (CLAUDE.md, ENGINEERING_GUIDELINES.md §16, ADR-005 clarification). The pre-public audit found no secrets or personal documents in the files or history. Commit author metadata includes a personal email address, which the owner accepted as public. New commits use the GitHub noreply address.
- 2026-09-25: Milestone 0 scaffold. The frontend uses ESLint (the Vite template's oxlint default was replaced to match ADR-004). The backend test client uses `httpx2`, which Starlette now expects. The backend floor is Python 3.12. Backend tests ignore `backend/.env` and inherited config variables (`tests/conftest.py`), so they are deterministic.
- 2026-09-24: ADR-004 accepted (React/Vite frontend, Python/FastAPI backend, Neon Postgres, Vercel Hobby, Render Free, GitHub Actions; $0/no-payment constraint).
- 2026-09-24: ADR-005 accepted (time-aware eligibility, provenance-aware profile ingestion, layered sources, open-source reuse policy).
- 2026-09-24: ADR-001, ADR-002, ADR-003 accepted.
