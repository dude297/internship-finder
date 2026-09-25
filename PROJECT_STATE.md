# Project State

> `PROJECT_STATE.md` must be updated after every meaningful implementation milestone or architecture change.

Last Updated: 2026-09-24
Current Milestone: Phase 0: Engineering documentation, governance, and architecture decisions
Current Production Version: None (not deployed)
Active Development Branch: main (remote: https://github.com/dude297/internship-finder)

## Current Objective

Finish Phase 0 architecture decisions (stack, source strategy, profile strategy) before any product implementation begins.

## Status Summary

Terms: **Selected** = decided in an ADR. **Provisioned** = account/project/resource actually created. **Implemented** = code exists and is tested.

| Area | Status |
|---|---|
| Technology stack | **Selected**, accepted via [ADR-004](docs/decisions/ADR-004-technology-stack.md). Not provisioned, not implemented. |
| Source/profile strategy | **Selected**, accepted via [ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md). Not implemented. |
| Operating cost constraint | $0/month, no payment method required ([ADR-004](docs/decisions/ADR-004-technology-stack.md#zero-cost--no-payment-constraint)) |
| Current user education state | High-school senior (expected to become an undergraduate after graduation) |
| Eligibility architecture | Temporal: status evaluated at the opportunity/requirement date (planned) |
| Profile ingestion | Planned |
| Résumé parsing | Planned |
| AI profile inference | Planned, optional, provenance-aware |
| Product implementation | Not started |
| Next milestone | Application scaffold |

### Selected stack (not provisioned)

| Layer | Selection | Provisioned? |
|---|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS | No |
| Frontend hosting | Vercel Hobby | No |
| Backend | Python, FastAPI, Pydantic | No |
| Backend hosting | Render Free Web Service | No |
| Database | Neon PostgreSQL Free (SQLAlchemy 2.x, Alembic, psycopg) | No |
| CI / scheduling | GitHub Actions (included free usage) | No |

## Completed Capabilities

- Engineering documentation framework (guidelines, operating contract, ADRs, topic docs).
- Architecture decisions ADR-001 through ADR-005.
- No product functionality has been implemented.

## In Progress

Nothing. ADR-004/ADR-005 documentation is awaiting review.

## Known Bugs

None. No application code exists.

## Known Technical Debt

- No application code, package manifests, or lint/typecheck/test/build tooling exist yet. The tools are selected (ADR-004) but not installed.

## Architecture Constraints

- Eligibility and fit are separate ([ADR-001](docs/decisions/ADR-001-separate-eligibility-and-fit.md)).
- All sources flow through a shared ingestion pipeline ([ADR-002](docs/decisions/ADR-002-shared-ingestion-pipeline.md)).
- AI is enrichment only, not source of truth, and optional ([ADR-003](docs/decisions/ADR-003-ai-as-enrichment.md)).
- React/Vite static frontend + Python/FastAPI backend + PostgreSQL. $0/month, no payment method. Any required paid dependency needs a new ADR ([ADR-004](docs/decisions/ADR-004-technology-stack.md)).
- Time-aware eligibility, provenance-aware profile facts, layered sources, and external repos as references only ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)).

## Database State

Selected: Neon PostgreSQL. Not provisioned. No schema or migrations exist.

## Current Scoring Version

Not implemented yet. Planned v1 documented in [docs/scoring.md](docs/scoring.md).

## Current Eligibility Rules Version

Not implemented yet. Planned v1 (temporal) documented in [docs/eligibility.md](docs/eligibility.md).

## Active Opportunity Sources

None. Planned sources and research references are listed in [docs/sources.md](docs/sources.md).

## Environment / Deployment Notes

- No environment variables are required yet.
- Hosting is selected (Vercel Hobby, Render Free, Neon Free) but not provisioned. See [docs/deployment.md](docs/deployment.md).
- Each provisioning step must confirm that no payment method is required before creating the account or project.

## Deferred Work

- Provisioning Vercel, Render, and Neon: deferred until there is code to deploy.
- CI workflows: deferred until the scaffold has lint/test/build commands.
- Profile schema, résumé parsing, AI inference, source adapters, eligibility, scoring: planned, not started.
- License verification for the `zshah101` and `SuryaHarikrishnan` reference repositories: needed before any use beyond reading.

## Next Planned Task

Review ADR-004/ADR-005. Then **application scaffold**: minimal `frontend/` (Vite + React + TS + Tailwind) and `backend/` (FastAPI) with lint, typecheck, test, and build commands, recorded in [docs/development.md](docs/development.md). No product features.

## Recent Important Decisions

- 2026-09-24: ADR-004 accepted (React/Vite frontend, Python/FastAPI backend, Neon Postgres, Vercel Hobby, Render Free, GitHub Actions; $0/no-payment constraint).
- 2026-09-24: ADR-005 accepted (time-aware eligibility, provenance-aware profile ingestion, layered sources, open-source reuse policy).
- 2026-09-24: ADR-001, ADR-002, ADR-003 accepted.
