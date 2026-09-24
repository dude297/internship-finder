# Project State

> `PROJECT_STATE.md` must be updated after every meaningful implementation milestone or architecture change.

Last Updated: 2026-09-24
Current Milestone: Phase 0 — Engineering documentation and governance setup
Current Production Version: None (not deployed)
Active Development Branch: main (remote: https://github.com/dude297/internship-finder)

## Current Objective

Establish engineering documentation, workflow rules, and handoff files before any product implementation begins.

## Completed Capabilities

- Engineering documentation framework (guidelines, operating contract, ADRs, topic docs).
- No product functionality has been implemented.

## In Progress

Nothing. Phase 0 documentation is awaiting review.

## Known Bugs

None. No application code exists.

## Known Technical Debt

- No application stack chosen; no package manifest, lint, typecheck, test, or build tooling exists.

## Architecture Constraints

- Eligibility and fit are separate ([ADR-001](docs/decisions/ADR-001-separate-eligibility-and-fit.md)).
- All sources flow through a shared ingestion pipeline ([ADR-002](docs/decisions/ADR-002-shared-ingestion-pipeline.md)).
- AI is enrichment only, not source of truth ([ADR-003](docs/decisions/ADR-003-ai-as-enrichment.md)).

## Database State

Not configured yet. No schema or migrations exist.

## Current Scoring Version

Not implemented yet. Planned v1 documented in [docs/scoring.md](docs/scoring.md).

## Current Eligibility Rules Version

Not implemented yet. Planned rules documented in [docs/eligibility.md](docs/eligibility.md).

## Active Opportunity Sources

None. Planned sources listed in [docs/sources.md](docs/sources.md).

## Environment / Deployment Notes

- No environment variables are required yet.
- Deployment is not configured yet.

## Deferred Work

- Stack selection (framework, database, hosting): TBD during Phase 1.
- CI/CD: not set up; deferred until tooling exists.

## Next Planned Task

Review of Phase 0 documentation, then choose/scaffold the application stack and record it as ADR-004 (TBD during Phase 1).

## Recent Important Decisions

- 2026-09-24: ADR-001, ADR-002, ADR-003 accepted.
