# Project State

> `PROJECT_STATE.md` must be updated after every meaningful implementation milestone or architecture change.

Last Updated: 2026-09-25
Current Milestone: Milestone 0: Development Foundation (implemented on `feature/application-scaffold`, awaiting review)
Current Production Version: None (not deployed)
Active Development Branch: `feature/application-scaffold`, stacked on `docs/stack-and-ingestion-adrs` ([PR #1](https://github.com/dude297/internship-finder/pull/1), not yet merged). Remote: https://github.com/dude297/internship-finder

## Current Objective

Review and merge the Milestone 0 scaffold, then start Milestone 1 (core domain/data model design).

## Status Summary

Terms: **Selected** = decided in an ADR. **Provisioned** = account/project/resource actually created. **Implemented** = code exists and is tested.

| Area | Status |
|---|---|
| Technology stack | **Selected** ([ADR-004](docs/decisions/ADR-004-technology-stack.md)). Scaffolded locally. Not provisioned. |
| Source/profile strategy | **Selected** ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)). Not implemented. |
| Operating cost constraint | $0/month, no payment method required ([ADR-004](docs/decisions/ADR-004-technology-stack.md#zero-cost--no-payment-constraint)) |
| Current user education state | High-school senior (expected to become an undergraduate after graduation) |
| Development foundation | **Implemented** (Milestone 0) |
| Product implementation | Not started |
| Next milestone | Milestone 1: core domain/data model design and initial migrations |

### Selected stack

| Layer | Selection | Scaffolded locally? | Provisioned? |
|---|---|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS, Zod | Yes (`frontend/`) | — |
| Frontend hosting | Vercel Hobby | — | No |
| Backend | Python 3.12+, FastAPI, Pydantic | Yes (`backend/`) | — |
| Backend hosting | Render Free Web Service | — | No |
| Database | Neon PostgreSQL Free (SQLAlchemy 2.x, Alembic, psycopg) | Yes (base, session, empty Alembic env) | No |
| CI | GitHub Actions (included free usage) | Yes (`.github/workflows/ci.yml`, PR/push only) | Not yet run on GitHub |

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

## Not Implemented

- Production infrastructure. No Neon provisioning, Vercel deployment, or Render deployment.
- Authentication
- Profile ingestion and résumé parsing
- Opportunity ingestion and source adapters
- Eligibility, scoring, ranking
- AI

## In Progress

Nothing. Milestone 0 is awaiting review. PR #1 (ADR-004/ADR-005) is awaiting review and merge.

## Known Bugs

None known.

## Known Technical Debt

- Backend dependencies are range-pinned in `pyproject.toml` without a lock file, so backend installs aren't fully reproducible. The frontend has `package-lock.json`.
- No integration tests against a real Postgres, and no Playwright end-to-end tests yet.
- CI has never run on GitHub yet. The first push/PR will be its first run.

## Architecture Constraints

- Eligibility and fit are separate ([ADR-001](docs/decisions/ADR-001-separate-eligibility-and-fit.md)).
- All sources flow through a shared ingestion pipeline ([ADR-002](docs/decisions/ADR-002-shared-ingestion-pipeline.md)).
- AI is enrichment only, not source of truth, and optional ([ADR-003](docs/decisions/ADR-003-ai-as-enrichment.md)).
- React/Vite static frontend + Python/FastAPI backend + PostgreSQL. $0/month, no payment method. Any required paid dependency needs a new ADR ([ADR-004](docs/decisions/ADR-004-technology-stack.md)).
- Time-aware eligibility, provenance-aware profile facts, layered sources, and external repos as references only ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)).

## Database State

Selected: Neon PostgreSQL. Not provisioned. The Alembic environment exists with **no migrations** and **no tables**.

## Current Scoring Version

Not implemented yet. Planned v1 documented in [docs/scoring.md](docs/scoring.md).

## Current Eligibility Rules Version

Not implemented yet. Planned v1 (temporal) documented in [docs/eligibility.md](docs/eligibility.md).

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

**Milestone 1: core domain/data model design and initial migrations.** Not started.

## Recent Important Decisions

- 2026-09-25: Milestone 0 scaffold. The frontend uses ESLint (the Vite template's oxlint default was replaced to match ADR-004). The backend test client uses `httpx2`, which Starlette now expects. The backend floor is Python 3.12.
- 2026-09-24: ADR-004 accepted (React/Vite frontend, Python/FastAPI backend, Neon Postgres, Vercel Hobby, Render Free, GitHub Actions; $0/no-payment constraint).
- 2026-09-24: ADR-005 accepted (time-aware eligibility, provenance-aware profile ingestion, layered sources, open-source reuse policy).
- 2026-09-24: ADR-001, ADR-002, ADR-003 accepted.
