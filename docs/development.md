# Development

## Local Setup

The repository has two independently runnable apps: `frontend/` (Node) and `backend/` (Python). There's no monorepo tool. Run each app's commands from its own directory.

### Prerequisites

- Node.js 24 with npm (tested with Node 24.15, npm 11.16)
- Python 3.12 or newer (`requires-python = ">=3.12"` in `backend/pyproject.toml`; tested with 3.12)

### Frontend (`frontend/`)

```bash
cd frontend
npm install
cp .env.example .env.local   # optional: dev falls back to http://localhost:8000
npm run dev                  # http://localhost:5173
```

### Backend (`backend/`)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate     # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env          # optional: defaults work for local dev
uvicorn app.main:app --reload # http://localhost:8000, health at /api/health
```

`DATABASE_URL` is **not** needed to run the backend or its tests. Only Alembic and database code use it.

### Commands

These commands have all been run successfully in this repository.

| Check | Backend (in `backend/`, venv active) | Frontend (in `frontend/`) |
|---|---|---|
| Install | `pip install -e ".[dev]"` | `npm install` (CI: `npm ci`) |
| Dev server | `uvicorn app.main:app --reload` | `npm run dev` |
| Lint | `ruff check .` | `npm run lint` (ESLint) |
| Format check | `ruff format --check .` | `npm run format:check` (Prettier) |
| Format (write) | `ruff format .` | `npm run format` |
| Typecheck | `pyright` (strict) | `npm run typecheck` (`tsc -b`, strict) |
| Unit tests | `pytest -m "not postgres"` | `npm test` (Vitest + React Testing Library) |
| PostgreSQL tests | `pytest -m postgres` (needs `TEST_DATABASE_URL`, see below) | — |
| Build | — | `npm run build` (output in `frontend/dist/`) |
| Migrations | see [Migrations Workflow](#migrations-workflow) | — |

Not set up yet: Playwright end-to-end tests.

### Test boundary: unit vs PostgreSQL

- **Unit tests** (education resolver, eligibility rules, config, health) are pure and need no database.
- **PostgreSQL tests** (`@pytest.mark.postgres`: models, constraints, repositories, migrations) run against a real, disposable PostgreSQL database named by `TEST_DATABASE_URL`. The session fixture migrates it to head, each test runs in a rolled-back transaction, and `tests/test_migrations.py` downgrades to base and upgrades again. Never point `TEST_DATABASE_URL` at a database whose data you want to keep.
- SQLite is **not** used. Constraint, timezone, and foreign-key behavior differ enough that SQLite tests would be misleading.
- Without `TEST_DATABASE_URL`, PostgreSQL tests are skipped locally. In CI (`CI=true`) they fail instead of skipping.

Local PostgreSQL with Docker (optional, disposable, test-only credentials):

```bash
docker run -d --rm --name if-test-pg -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=internship_finder_test -p 127.0.0.1:5433:5432 postgres:18
export TEST_DATABASE_URL=postgresql+psycopg://test:test@127.0.0.1:5433/internship_finder_test
pytest                      # unit + PostgreSQL tests
docker stop if-test-pg      # the container and its data are removed
```

### Local frontend ↔ backend integration

1. Start the backend: `uvicorn app.main:app --reload` (port 8000).
2. Start the frontend: `npm run dev` (port 5173).
3. Open http://localhost:5173. "Backend status" should read **Healthy**. If the backend is stopped, it reads **Unavailable** with the error instead.

CORS allows only `FRONTEND_ORIGIN` (default `http://localhost:5173`). If you run the frontend on another port, set `FRONTEND_ORIGIN` in `backend/.env`.

### Environment variables

| Variable | App | Exposure | Required | Purpose |
|---|---|---|---|---|
| `VITE_API_BASE_URL` | frontend | **Public** (compiled into the browser bundle) | Production builds only (dev falls back to `http://localhost:8000`) | Backend base URL |
| `FRONTEND_ORIGIN` | backend | Server-only | No (default `http://localhost:5173`) | The single origin allowed by CORS. `*` is rejected. |
| `DATABASE_URL` | backend | Server-only, secret | No, not for the health-only scaffold | SQLAlchemy URL (`postgresql+psycopg://…`) for Alembic/database code |

Examples are in `frontend/.env.example` and `backend/.env.example`. Never commit `.env` files.

Backend tests ignore `backend/.env` and any of these variables set in your shell (`backend/tests/conftest.py`), so they run against defaults. Tests that need a value set it explicitly.

## Version Control

Git repository: https://github.com/dude297/internship-finder (default branch `main`).

## Branch Workflow

- `main` stays usable.
- One logical change per branch: `feature/…`, `fix/…`, `refactor/…`, `docs/…`.
- Conventional Commit-style messages (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`).

Details are in [ENGINEERING_GUIDELINES.md §3](../ENGINEERING_GUIDELINES.md#3-repository-workflow-rules).

## CI

GitHub Actions, within included free usage only. No paid runners, scheduled jobs, or deployment workflows.

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on pushes to `main` and on every pull request:

- Frontend (Node 24): `npm ci`, lint, format check, typecheck, tests, build
- Backend (Python 3.12): install, `ruff check`, `ruff format --check`, `pyright`, unit tests, then against an ephemeral PostgreSQL 18 service container (test-only credentials in the workflow, not secrets): `alembic upgrade head`, `alembic check` (models match migrations), `alembic downgrade base`, `alembic upgrade head`, and the PostgreSQL tests

Planned later: docs checks where practical.

## Test Workflow

- Unit tests for core logic (eligibility, scoring, normalization, dedupe, ranking, parsing), independent of the UI. These are Pytest tests in the backend.
- Eligibility tests cover temporal boundaries (before/after expected graduation and enrollment dates).
- Integration tests for DB, ingestion, API routes, and authorization.
- Bug fixes add regression tests where reasonable.

See [ENGINEERING_GUIDELINES.md §12](../ENGINEERING_GUIDELINES.md#12-testing-standards).

## Migrations Workflow

Alembic is set up in `backend/`. The first migration is `3b9c6b57bb60` (initial core domain schema). `alembic/env.py` uses `sqlalchemy.url` if it's set programmatically (the tests do this), otherwise `DATABASE_URL` from app settings. The autogenerate target is `app.models.Base.metadata`. Add new model modules to `app/models/__init__.py` so autogenerate sees them. Enum columns autogenerate duplicate CHECK constraints: keep one named `ck_…` constraint per enum and set `create_constraint=False` on the `sa.Enum` (see the initial migration).

From `backend/` with the venv active and `DATABASE_URL` set:

```bash
alembic revision --autogenerate -m "describe change"  # create a migration (review it before committing)
alembic upgrade head                                  # apply migrations
alembic downgrade -1                                  # roll back one migration
alembic upgrade head --sql                            # print SQL without connecting (offline mode)
alembic current                                       # show the applied revision
alembic check                                         # fail if models and migrations differ
```

Verified against PostgreSQL 18 (local Docker and CI): `upgrade head`, `check`, `downgrade base`, `upgrade head`. Without `DATABASE_URL`, Alembic commands fail with `DATABASE_URL must be set to run Alembic migrations`. No hosted database is provisioned yet. Rules:

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
