# Development

## Local Setup

**Not available yet.** The repository has no application code, package manifest, or scripts. There is nothing to install or run.

The tooling is **selected** ([ADR-004](decisions/ADR-004-technology-stack.md)) but not installed. When the application scaffold lands, this section must list the **actual** commands:

| Check | Backend (Python) | Frontend (TypeScript) |
|---|---|---|
| Install | TBD | TBD |
| Dev server | TBD (FastAPI) | TBD (Vite) |
| Lint | TBD (Ruff) | TBD (ESLint) |
| Format | TBD (Ruff) | TBD (Prettier) |
| Typecheck | TBD (Pyright or equivalent) | TBD (`tsc`, strict) |
| Unit tests | TBD (Pytest) | TBD (Vitest) |
| Integration tests | TBD (Pytest) | — |
| End-to-end tests | TBD (Playwright) | TBD (Playwright) |
| Migrations | TBD (Alembic) | — |
| Build | — | TBD (Vite) |

Tool names in parentheses are selections, not working commands. Only document commands that exist in the repo.

## Version Control

Git repository: https://github.com/dude297/internship-finder (default branch `main`).

## Branch Workflow

- `main` stays usable.
- One logical change per branch: `feature/…`, `fix/…`, `refactor/…`, `docs/…`.
- Conventional Commit-style messages (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`).

Details are in [ENGINEERING_GUIDELINES.md §3](../ENGINEERING_GUIDELINES.md#3-repository-workflow-rules).

## CI (planned)

GitHub Actions, within included free usage only. No paid runners. When it's set up, it should run:

- Backend: Ruff, type checks, Pytest
- Frontend: lint, TypeScript check, Vitest, build
- Repository: migration validation and docs checks where practical

Not configured yet.

## Test Workflow

- Unit tests for core logic (eligibility, scoring, normalization, dedupe, ranking, parsing), independent of the UI. These are Pytest tests in the backend.
- Eligibility tests cover temporal boundaries (before/after expected graduation and enrollment dates).
- Integration tests for DB, ingestion, API routes, and authorization.
- Bug fixes add regression tests where reasonable.

See [ENGINEERING_GUIDELINES.md §12](../ENGINEERING_GUIDELINES.md#12-testing-standards).

## Migrations Workflow

Not applicable yet (no database). Once Neon Postgres is provisioned:

- every schema change is an Alembic migration, committed with the code that needs it
- update [data-model.md](data-model.md) in the same change
- review migrations before merging
- no manual production schema changes

## Documentation Expectations

Documentation updates are part of Definition of Done. See [ENGINEERING_GUIDELINES.md §15](../ENGINEERING_GUIDELINES.md#15-documentation-maintenance-rules) for which doc to update for which change.

## Feature Completion Workflow

1. Read relevant code, docs, [PROJECT_STATE.md](../PROJECT_STATE.md), and ADRs.
2. Plan: files, schema/API impact, assumptions, risks, tests.
3. Implement the minimum correct change on a feature branch.
4. Validate: lint, typecheck, tests, build, and migrations where applicable.
5. Update docs and `PROJECT_STATE.md`.
6. Report using the format in [CLAUDE.md](../CLAUDE.md).
7. Review. The work isn't done until it's reviewed.
