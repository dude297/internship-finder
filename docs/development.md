# Development

## Local Setup

**Not available yet.** The repository has no application code, package manifest, or scripts. There is nothing to install or run.

When the stack is scaffolded (Phase 1), this section must list the **actual** commands for:

| Check | Command |
|---|---|
| Install | TBD |
| Dev server | TBD |
| Lint | TBD |
| Typecheck | TBD |
| Unit tests | TBD |
| Integration tests | TBD |
| Build | TBD |

Only document commands that exist in the repo.

## Version Control

The repository is not yet initialized as a git repository. Once it is, follow the rules below.

## Branch Workflow

- `main` stays usable.
- One logical change per branch: `feature/…`, `fix/…`, `refactor/…`, `docs/…`.
- Conventional Commit-style messages (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`).

Details are in [ENGINEERING_GUIDELINES.md §3](../ENGINEERING_GUIDELINES.md#3-repository-workflow-rules).

## Test Workflow

- Unit tests for core logic (eligibility, scoring, normalization, dedupe, ranking, parsing), independent of the UI.
- Integration tests for DB, ingestion, API routes, and auth/RLS.
- Bug fixes add regression tests where reasonable.

See [ENGINEERING_GUIDELINES.md §12](../ENGINEERING_GUIDELINES.md#12-testing-standards).

## Migrations Workflow

Not applicable yet (no database). Once a database exists:

- every schema change is a migration, committed with the code that needs it
- update [data-model.md](data-model.md) in the same change
- review migrations (and RLS policies, if used) before merging
- no manual production schema changes

## Documentation Expectations

Documentation updates are part of Definition of Done. See [ENGINEERING_GUIDELINES.md §15](../ENGINEERING_GUIDELINES.md#15-documentation-maintenance-rules) for which doc to update for which change.

## Feature Completion Workflow

1. Read relevant code, docs, [PROJECT_STATE.md](../PROJECT_STATE.md), and ADRs.
2. Plan: files, schema/API impact, assumptions, risks, tests.
3. Implement the minimum correct change on a feature branch.
4. Validate: lint, typecheck, tests, build, and migrations/RLS where applicable.
5. Update docs and `PROJECT_STATE.md`.
6. Report using the format in [CLAUDE.md](../CLAUDE.md).
7. Review. The work isn't done until it's reviewed.
