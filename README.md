# Personal Internship Finder

A personal, single-user tool for finding internship and research opportunities, checking eligibility against a personal profile, and ranking them by fit. Eligibility is time-aware: the current user is a high-school senior, and opportunities are evaluated against their expected status when each one begins (for example, as an incoming undergraduate).

**Intended user:** a single user (the repository owner). It's still being built to production standards.

> ⚠️ **Status: development foundation only (Milestone 0).** A frontend and backend scaffold exists and shows backend health. No product features are implemented. The capabilities described in `docs/` are **planned**. See [PROJECT_STATE.md](PROJECT_STATE.md) for the current state.

## Stack

**Scaffolded locally, not provisioned or deployed** ([ADR-004](docs/decisions/ADR-004-technology-stack.md)):

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, built as a static client-side app and hosted on Vercel Hobby
- **Backend:** Python, FastAPI, Pydantic, hosted on a Render Free Web Service
- **Database:** Neon PostgreSQL Free, accessed with SQLAlchemy 2.x, Alembic, and psycopg
- **CI / scheduling:** GitHub Actions (included free usage)
- **Testing:** Pytest, Vitest, Playwright

**Hard constraint:** $0/month, and no payment method required for any required service.

Opportunity sourcing and profile ingestion strategy: [ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md).

## Local Development

Requires Node.js 24 and Python 3.12+. The frontend and backend run independently.

```bash
# Backend: http://localhost:8000/api/health
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload

# Frontend: http://localhost:5173 (in a second terminal)
cd frontend
npm install
npm run dev
```

The page should show "Backend status: Healthy". Lint, typecheck, test, and build commands are in [docs/development.md](docs/development.md).

## Public Repository

This repository contains application source code only. Personal résumé, profile, application, and credential data must never be committed. See [CLAUDE.md](CLAUDE.md#public-repository-safety).

## Environment

Each app has its own example file: [`frontend/.env.example`](frontend/.env.example) and [`backend/.env.example`](backend/.env.example). None of the variables are required for local development. `DATABASE_URL` isn't used by the health-only scaffold. Never commit real values.

## Documentation

| Document | Purpose |
|---|---|
| [ENGINEERING_GUIDELINES.md](ENGINEERING_GUIDELINES.md) | Authoritative engineering standards |
| [CLAUDE.md](CLAUDE.md) | Operating contract for AI implementation sessions |
| [PROJECT_STATE.md](PROJECT_STATE.md) | Living handoff: current state and next task |
| [CHANGELOG.md](CHANGELOG.md) | Notable changes |
| [docs/architecture.md](docs/architecture.md) | Current vs. planned architecture |
| [docs/development.md](docs/development.md) | Setup and workflow |
| [docs/deployment.md](docs/deployment.md) | Deployment process |
| [docs/data-model.md](docs/data-model.md) | Database entities |
| [docs/eligibility.md](docs/eligibility.md) | Eligibility rules |
| [docs/scoring.md](docs/scoring.md) | Fit scoring model |
| [docs/sources.md](docs/sources.md) | Opportunity source registry |
| [docs/operations.md](docs/operations.md) | Runtime operations and monitoring |
| [docs/decisions/](docs/decisions/) | Architecture decision records |
