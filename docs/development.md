# Development

## Local Setup

The repository has two independently runnable apps, `frontend/` (Node) and `backend/` (Python), plus a local-only PostgreSQL in `compose.yaml`. There's no monorepo tool. Run each app's commands from its own directory.

### Prerequisites

- Node.js 24 with npm (tested with Node 24.15, npm 11.16)
- Python 3.12 or newer (`requires-python = ">=3.12"` in `backend/pyproject.toml`; tested with 3.12)
- Docker with Compose (tested with Docker 29.7), for the local PostgreSQL 18. Any other PostgreSQL works too.

### Run the private app locally

Verified on 2026-09-27 (Windows, Git Bash, existing venv and `node_modules`): `docker compose up -d`, `alembic upgrade head`, uvicorn, `npm run dev`, and requests through the Vite proxy. Owner creation was exercised through `--password-stdin` (E2E setup and CLI tests); the interactive `getpass` prompt is covered by a CLI test with `getpass` stubbed.

```bash
# 1. Database: PostgreSQL 18 on 127.0.0.1:5432 with local-only placeholder credentials.
#    Your data lives in the `pgdata` Docker volume, never in the repository.
docker compose up -d

# 2. Backend (first terminal)
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -r requirements-dev.lock && pip install --no-deps -e .   # or: pip install -e ".[dev]"
cp .env.example .env               # DATABASE_URL points at the Compose database
alembic upgrade head
python -m app.cli create-owner --username <your-username>   # prompts for the password twice
uvicorn app.main:app --reload      # http://localhost:8000

# 3. Frontend (second terminal)
cd frontend
npm install
npm run dev                        # http://localhost:5173 (proxies /api to :8000)
```

Open http://localhost:5173, log in, and fill in your profile. Your real profile and applications are entered only through the app and stay in the local database.

- The password is read with `getpass`: it isn't echoed, printed, or saved in shell history. Never pass it as a command-line argument. The minimum length is 12.
- `create-owner` refuses if an owner already exists. To change the password: `python -m app.cli set-password --username <your-username>` (this also logs out every session).
- There is no registration page and no password-reset email. Losing the password means running `set-password` on the machine with the database.
- Stop the database with `docker compose stop`. `docker compose down -v` **deletes** the volume and all your data.

### Same-origin development

The browser only talks to the Vite dev server. Vite proxies `/api/*` to `http://localhost:8000` (`frontend/vite.config.ts`), so the session cookie is same-origin and the backend needs no CORS. The backend deliberately sends no CORS headers ([ADR-007 §6](decisions/ADR-007-single-user-auth-and-private-api.md#6-same-origin-api)). `vite preview` has the same proxy.

The session cookie is `Secure` by default. Chrome and Firefox accept Secure cookies on `http://localhost`, so local development works without changes. Set `SESSION_COOKIE_SECURE=false` in `backend/.env` only if you use plain HTTP on a different host name.

### Commands

These commands have all been run successfully in this repository.

| Check | Backend (in `backend/`, venv active) | Frontend (in `frontend/`) |
|---|---|---|
| Install | `pip install -r requirements-dev.lock && pip install --no-deps -e .` (locked, as CI; `pip install -e ".[dev]"` also works) | `npm install` (CI: `npm ci`) |
| Re-lock dependencies | after any `pyproject.toml` dependency change, see [Dependency lock](#dependency-lock) | — |
| Dev server | `uvicorn app.main:app --reload` | `npm run dev` |
| Lint | `ruff check .` | `npm run lint` (ESLint) |
| Format check | `ruff format --check .` | `npm run format:check` (Prettier) |
| Format (write) | `ruff format .` | `npm run format` |
| Typecheck | `pyright` (strict) | `npm run typecheck` (`tsc -b`, strict) |
| Unit tests | `pytest -m "not postgres"` | `npm test` (Vitest + React Testing Library) |
| PostgreSQL tests | `pytest -m postgres` (needs `TEST_DATABASE_URL`, see below) | — |
| End-to-end | — | `npm run test:e2e` (Playwright, needs `E2E_DATABASE_URL`, see below) |
| Build | — | `npm run build` (output in `frontend/dist/`) |
| Migrations | see [Migrations Workflow](#migrations-workflow) | — |
| Docs check | `python scripts/check_docs.py` (repository root; add `--base origin/main` for the changed-path guards; `--write-status` regenerates the status blocks from `docs/status.json`); tests: `python -m unittest discover -s scripts/tests` | — |
| Owner account | `python -m app.cli create-owner` / `set-password` | — |
| Source sync | `python -m app.cli sync-sources` / `sync-source <id-or-key>` (live network) | — |
| Requirement scan | `python -m app.cli scan-requirements` (refreshes requirement suggestions for stored opportunities; writes only suggestions, [ADR-012](decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)) | — |
| Source coverage | `python -m app.cli source-coverage` (read-only; counts only, no network) | — |
| Performance smoke | `PERF_DATABASE_URL=<disposable db> python scripts/perf_smoke.py` (manual; replaces that database's opportunities, profile, and profile sources; also times a résumé review batch) | — |
| Source sync performance | `PERF_DATABASE_URL=<disposable db> python scripts/perf_sources.py` (manual; wipes that database's opportunities and non-built-in sources; times 10/25/50-board syncs, discovery, and the list query, [operations.md](operations.md#operational-source-cap)) | — |

### Dependency lock

`backend/requirements.lock` (runtime) and `backend/requirements-dev.lock` (runtime + `dev` extra) pin every backend dependency, transitively, with SHA-256 hashes, resolved for Python 3.12 on every platform (`--universal`, so platform markers such as `uvloop` and `colorama` are kept). `pyproject.toml` still holds the allowed ranges; the locks are what CI, the E2E job, and the scheduled production sync install (`pip install -r <lock>`, then the app with `--no-deps`, so a dependency missing from the lock fails the install or the first import instead of being silently resolved).

Regenerate both after changing a dependency in `pyproject.toml` (uv is a free, MIT/Apache-licensed developer tool; it is not a runtime dependency):

```bash
cd backend
pip install uv     # or any uv install
uv pip compile pyproject.toml --universal --python-version 3.12 --generate-hashes -o requirements.lock
uv pip compile pyproject.toml --extra dev --universal --python-version 3.12 --generate-hashes -o requirements-dev.lock
```

Upgrading a pinned version is the same command with `--upgrade-package <name>` (or `--upgrade`). Render still builds with `pip install .` until its build command is switched to the lock ([deployment.md](deployment.md#render-internship-finder-api)).

### Test boundary: unit vs PostgreSQL vs end-to-end

- **Unit tests** (education resolver, eligibility rules, fit scoring and its text matcher, the fit fingerprint, the internship title filter, password hashing, CSRF, throttle, config, health, the ingestion HTTP client, HTML-to-text, URL canonicalization, adapters, the evaluation fingerprint) are pure and need no database. Since Milestone 7: `tests/test_feed_provider_identity.py`, pure unit tests of the feed adapter's `provider_identity` function (the Greenhouse/Lever/Ashby rules shared by deduplication and discovery, [ADR-013 §2](decisions/ADR-013-provider-enrichment-and-source-authority.md#2-ats-source-discovery)).
- **Résumé parser tests** (`tests/test_resume_parser.py`, Milestone 5) are unit tests too. They build synthetic text and PDF files in code (`tests/resume_fixtures.py`: a hand-written PDF writer, an encrypted PDF, and a flate-bomb PDF); no real résumé is ever used. PDF extraction runs in a spawned child process ([ADR-011](decisions/ADR-011-profile-source-ingestion-and-review.md)), so those tests start Python subprocesses; the bomb test waits for a shortened 3 s time limit.
- **No test calls a real job board.** Ingestion tests serve fabricated provider payloads (`tests/ingestion_fixtures.py`: "Example Robotics", "Example Institute", fictional dates) through an in-memory `httpx2` transport. Live sources are exercised only by the manual smoke test below.
- **PostgreSQL tests** (`@pytest.mark.postgres`: models, constraints, repositories, migrations, the owner CLI, and the whole HTTP API through FastAPI's `TestClient`) run against a real, disposable PostgreSQL database named by `TEST_DATABASE_URL`. The session fixture migrates it to head, each test runs in a rolled-back transaction (the API's commits become savepoints), and `tests/test_migrations.py` steps down through the Milestone 1 revision to base and back up. Never point `TEST_DATABASE_URL` at a database whose data you want to keep. Since Milestone 7: `tests/test_source_authority.py` (rank, tie-break, takeover, and fallback-from-stored-payload over real opportunity/source rows, ADR-013 §1, §4, §5) and `tests/test_source_discovery.py` (the `source-coverage` CLI, `GET /api/sources/discovery`, and `POST /api/sources/discovery/add`, including the 25-item all-or-nothing limit and already-configured skips, ADR-013 §2–§3), both PostgreSQL tests since they exercise real deduplication and persistence.
- **Milestone 8.1** ([ADR-015](decisions/ADR-015-freshness-requirements-v2-and-independent-discovery.md)): unit `tests/test_freshness_unit.py` (freshness derivation), `tests/test_requirement_extractor_v2.py` (the 258-sentence synthetic corpus in `tests/requirement_corpus_v2.py`, v1-vs-v2 table against the frozen test-only `tests/_extractor_v1_reference.py`), `tests/test_requirement_extractor_v2_adversarial.py`, `tests/test_workable_adapter.py`, `tests/test_pinpoint_adapter.py`; PostgreSQL `tests/test_m81_freshness.py` (freshness states/filters, discovered filter, constant list statement count, independent coverage, Direct Source Catalog API and file validation), `tests/test_m81_extractor_rescan.py` (v1→v2 rescan keeps reviewed decisions), `tests/test_m81_adapters_adversarial.py`, and `tests/test_feed_off_resilience.py` (the whole product with the community feed disabled or failing).
- **Frontend component tests** stub `fetch`, so they need no backend.
- **End-to-end tests** (`frontend/e2e/`) run the real stack in Chromium against a disposable database named by `E2E_DATABASE_URL`.
- SQLite is **not** used. Constraint, timezone, and foreign-key behavior differ enough that SQLite tests would be misleading.
- Without `TEST_DATABASE_URL`, PostgreSQL tests are skipped locally. In CI (`CI=true`) they fail instead of skipping.
- All test data and credentials are synthetic.

Test databases on the Compose server (disposable, separate from your `internship_finder` database):

```bash
docker compose exec postgres psql -U internship_finder -c "CREATE DATABASE internship_finder_test"
docker compose exec postgres psql -U internship_finder -c "CREATE DATABASE internship_finder_e2e"
export TEST_DATABASE_URL=postgresql+psycopg://internship_finder:local-dev-only@127.0.0.1:5432/internship_finder_test
pytest                      # unit + PostgreSQL tests (in backend/)
```

Or a throwaway container:

```bash
docker run -d --rm --name if-test-pg -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=internship_finder_test -p 127.0.0.1:5433:5432 postgres:18
export TEST_DATABASE_URL=postgresql+psycopg://test:test@127.0.0.1:5433/internship_finder_test
```

### End-to-end tests (Playwright)

```bash
cd frontend
npx playwright install chromium    # once
export E2E_DATABASE_URL=postgresql+psycopg://internship_finder:local-dev-only@127.0.0.1:5432/internship_finder_e2e
npm run test:e2e
```

`playwright.config.ts` starts uvicorn on :8000 (with `DATABASE_URL=$E2E_DATABASE_URL`) and Vite on :5173, so stop your own dev servers first. The global setup runs `alembic upgrade head` and creates the synthetic owner (`e2e-synthetic-owner`) through the CLI with `--password-stdin`, or resets its password if an earlier run created it. `E2E_DATABASE_URL` has no default, so the tests can't touch your development database by accident. Set `E2E_PYTHON` if the backend virtualenv isn't `backend/.venv`.

`e2e/ingestion.spec.ts` covers ingestion without the network: the backend's test-only `INGESTION_FIXTURE_FILE` (set by `playwright.config.ts` to a file in the OS temp directory) maps source URLs to synthetic JSON bodies, and the test rewrites it between syncs. It adds a Greenhouse board by link, syncs twice (created, then unchanged), opens an imported opportunity (needs verification, unassessed), reviews its requirements to complete (eligible), tracks a second posting, then publishes a snapshot where the first is renamed upstream and the second is gone: the review survives, and the second posting is closed (not deleted) with its tracking intact. Board and organization names are unique per run, so it's repeatable on a reused database.

`e2e/fit.spec.ts` (Milestone 4): log in; save an eligibility profile and a Match Profile (one skill, an interest, work mode, availability); create four postings through the same-origin API (two eligible, one unassessed, one with an impossible minimum age); check the recommended order (eligible by fit, then needs verification, then ineligible even though it matches best); open "Why this match?"; change the skill and save once; see the eligible pair swap while eligibility still dominates; log out and back in and confirm the Match Profile and order persisted. All terms are unique per run, so it's repeatable on a reused database. The ingestion spec also checks that a new board defaults to **Internships only** (a full-time posting is **Filtered**), and a second ingestion test switches a board to **All postings** and back (created, then closed).

`e2e/profile-sources.spec.ts` (Milestone 5): log in; save a Match Profile skill; create two postings through the API, one mentioning a unique imported skill; upload a synthetic plain-text résumé on **Imported Profile** (content unique per run, so the SHA-256 never repeats); check that pending facts leave fit unchanged; accept the skill, edit and accept a project, reject an award, and apply once ("Scoring refreshed"); see the posting move up and "Why this match?" name the skill; log out and in and check the review state persisted; delete the source and check fit falls back exactly while the Match Profile skill stays. A second test builds a synthetic PDF in TypeScript (`e2e/fixtures/make-pdf.ts`), uploads it, and deletes it.

`e2e/source-coverage.spec.ts` (Milestone 7): network-free through the same `INGESTION_FIXTURE_FILE` mechanism as `e2e/ingestion.spec.ts`. Log in; sync the discovery feed fixture so it creates a feed-only opportunity whose ID proves an Ashby board; open the Sources page's coverage section and check it reports the opportunity as feed-only and enrichable; add the suggested Ashby board and sync its fixture; check the opportunity's canonical description switches to the board's text (takeover) and coverage moves it out of feed-only; all synthetic, no real network call.

The original scenario (`e2e/workflow.spec.ts`): a wrong password is rejected; log in; create the profile; add a manual opportunity with a minimum-age and an incoming-undergraduate requirement, marked complete; see **Eligible** with the projected-status notice; change the date of birth and see **Ineligible** after automatic re-evaluation; track the application as Applied with a date and notes; log out; confirm the UI redirects and the API returns `401`; log back in and confirm everything persisted. Failure traces and screenshots go to `frontend/test-results/` (gitignored).

### Environment variables

| Variable | App | Exposure | Required | Purpose |
|---|---|---|---|---|
| `DATABASE_URL` | backend | Server-only, secret in real deployments | For the private API, the owner CLI, and Alembic (not for `/api/health`) | SQLAlchemy URL (`postgresql+psycopg://…`). `backend/.env.example` points at the Compose database |
| `SESSION_TTL_HOURS` | backend | Server-only | No (default `24`, 1–720) | Absolute session lifetime |
| `SESSION_COOKIE_SECURE` | backend | Server-only | No (default `true`) | `Secure` cookie attribute. Only set `false` for plain-HTTP development on a non-localhost host |
| `HOSTED` | backend | Server-only | No (default `false`) | Hosted mode (Render): hides `/docs`, `/redoc`, `/openapi.json`; refuses to start unless `SESSION_COOKIE_SECURE=true` ([ADR-009](decisions/ADR-009-hosted-deployment-architecture.md)) |
| `PROXY_SHARED_SECRET` | backend (and Vercel Production) | **Secret**, server-only | No (hosted only) | ≥ 32 random characters. Requests carrying it in `X-IF-Proxy-Secret` share the `proxy` login-throttle bucket; everything else shares `direct`. Forwarding headers are never read. Unset locally |
| `TEST_DATABASE_URL` | backend tests | Local/CI only | For PostgreSQL tests | Disposable test database |
| `E2E_DATABASE_URL` | Playwright | Local/CI only | For `npm run test:e2e` | Disposable E2E database |
| `E2E_OWNER_USERNAME`, `E2E_OWNER_PASSWORD` | Playwright | Local/CI only, synthetic | No (synthetic defaults) | The throwaway owner the E2E test logs in as |
| `E2E_PYTHON` | Playwright | Local only | No | Backend Python executable |
| `INGESTION_FIXTURE_FILE` | backend | **Test-only** | No (unset = real network) | JSON file `{url: body}` that source sync reads instead of the network. Set only by the E2E config for its disposable database; the backend logs a warning while it's active. Never set it for real use |

The frontend has **no** build-time environment variables: it calls relative `/api` URLs. (Vercel's Production environment holds `PROXY_SHARED_SECRET` for the `/api` rewrite only; it never reaches the bundle.) (`VITE_API_BASE_URL` and the backend's `FRONTEND_ORIGIN` were removed in Milestone 2.) There's no cookie-signing secret because sessions are opaque database rows.

The example is `backend/.env.example`. Never commit `.env` files.

Backend tests ignore `backend/.env` and any of these variables set in your shell (`backend/tests/conftest.py`), so they run against defaults. Tests that need a value set it explicitly.

### Syncing sources locally

The Sources page (`/sources`) syncs on demand. The same pipeline runs from the command line (in `backend/`, venv active, `DATABASE_URL` set):

```bash
python -m app.cli sync-sources                                         # every enabled source
python -m app.cli sync-source community_feed:zshah-tech-internships    # one source, by key or ID
```

These call real public APIs (see [sources.md](sources.md)). Be courteous: sync when you need fresh data, not in a loop; an unchanged feed answers `304` and costs almost nothing. Output is counts only. The exit code is `1` when a requested sync failed.

**Live smoke test (manual, never in CI).** Use a disposable database, not your own: create one (`CREATE DATABASE internship_finder_smoke`), `alembic upgrade head` against it, run `sync-source community_feed:zshah-tech-internships` twice, and check the second run is `no_change` (or all `unchanged` if the feed changed its validators). Never commit downloaded payloads.

## Version Control

Git repository: https://github.com/dude297/internship-finder (default branch `main`).

## Branch Workflow

- `main` stays usable.
- One logical change per branch: `feature/…`, `fix/…`, `refactor/…`, `docs/…`.
- Conventional Commit-style messages (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`).

Details are in [ENGINEERING_GUIDELINES.md §3](../ENGINEERING_GUIDELINES.md#3-repository-workflow-rules).

## CI

GitHub Actions, within included free usage only. No paid runners and no deployment workflows (Render and Vercel deploy from `main` themselves). The one scheduled workflow, [`sync-production.yml`](../.github/workflows/sync-production.yml), is the production source sync, not a check ([operations.md](operations.md)).

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on pushes to `main` and on every pull request:

- Docs (Python, standard library only): the checker's own tests, `scripts/check_docs.py` repository checks, and the changed-path guards against the PR base (or the pushed range) ([docs/README.md](README.md#enforcement))
- Frontend (Node 24): `npm ci`, lint, format check, typecheck, tests, build
- Backend (Python 3.12): install, `ruff check`, `ruff format --check`, `pyright`, unit tests, then against an ephemeral PostgreSQL 18 service container (test-only credentials in the workflow, not secrets): `alembic upgrade head`, `alembic check` (models match migrations), `alembic downgrade base`, `alembic upgrade head`, and the PostgreSQL tests (including the API and CLI)
- No CI job calls a third-party job board; ingestion is tested with synthetic fixtures only
- E2E: its own ephemeral PostgreSQL 18, backend install, `npm ci`, Playwright Chromium, and `npx playwright test` with synthetic, clearly labeled test-only owner credentials in the workflow `env` (no repository secrets). On failure it uploads the Playwright report and traces (synthetic data only) for 7 days

Planned later: docs checks where practical.

## Test Workflow

- Unit tests for core logic (eligibility, scoring, normalization, dedupe, ranking, parsing), independent of the UI. These are Pytest tests in the backend.
- Eligibility tests cover temporal boundaries (before/after expected graduation and enrollment dates).
- Integration tests for DB, ingestion, API routes, and authorization (`tests/test_api_*.py`, `tests/test_cli.py`).
- Playwright end-to-end tests for the critical private workflow (`frontend/e2e/`).
- Bug fixes add regression tests where reasonable.

See [ENGINEERING_GUIDELINES.md §12](../ENGINEERING_GUIDELINES.md#12-testing-standards).

## Migrations Workflow

Alembic is set up in `backend/`. The revision list (ten, linear, head `b7e3d9f1a2c4`) and what each one changes are in [data-model.md](data-model.md#current-database-state). Merged migrations are **immutable**: never edit them. Schema changes are new revisions. Two early development databases migrated with pre-merge local versions of `7d7f4f8b9a3c` and `726372d627b8` are repaired automatically by `alembic upgrade head` ([graduation constraint](data-model.md#graduation-constraint-reconciliation-726372d627b8), [running-run index](data-model.md#running-run-index-reconciliation-92a17353e5a8)); no manual SQL is needed. `alembic/env.py` uses `sqlalchemy.url` if it's set programmatically (the tests do this), otherwise `DATABASE_URL` from app settings. The autogenerate target is `app.models.Base.metadata`. Add new model modules to `app/models/__init__.py` so autogenerate sees them. Enum columns autogenerate duplicate CHECK constraints: keep one named `ck_…` constraint per enum and set `create_constraint=False` on the `sa.Enum` (see the initial migration). `tests/test_migrations.py` covers each revision's round trip and guards.

From `backend/` with the venv active and `DATABASE_URL` set:

```bash
alembic revision --autogenerate -m "describe change"  # create a migration (review it before committing)
alembic upgrade head                                  # apply migrations
alembic downgrade -1                                  # roll back one migration
alembic upgrade head --sql                            # print SQL without connecting (offline mode)
alembic current                                       # show the applied revision
alembic check                                         # fail if models and migrations differ
```

Verified against PostgreSQL 18 (local Docker and CI): `upgrade head`, `check`, `downgrade 7d7f4f8b9a3c`, `downgrade 3b9c6b57bb60`, `downgrade base`, `upgrade head`, `check` (CI skips the intermediate downgrades; `tests/test_migrations.py` covers them, plus the stale-`7d7f4f8b9a3c` repair). Without `DATABASE_URL`, Alembic commands fail with `DATABASE_URL must be set to run Alembic migrations`. The hosted database (Neon Free) is migrated to the current head; see [deployment.md](deployment.md). Rules:

- every schema change is an Alembic migration, committed with the code that needs it
- update [data-model.md](data-model.md) in the same change
- review migrations before merging
- no manual production schema changes

## Documentation Expectations

Documentation is part of Definition of Done: [ENGINEERING_GUIDELINES.md §15](../ENGINEERING_GUIDELINES.md#15-documentation-maintenance-rules) (what to update) and [docs/README.md](README.md) (document authority). Check locally with `python scripts/check_docs.py` (add `--base origin/main` on a branch to run the changed-path guards CI runs).

## Feature Completion Workflow

The workflow is defined once, in [ENGINEERING_GUIDELINES.md §4](../ENGINEERING_GUIDELINES.md#4-implementation-workflow); completion reporting is in [CLAUDE.md](../CLAUDE.md#workflow).
