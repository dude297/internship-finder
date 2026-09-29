# Personal Internship Finder

A personal, single-user tool for finding internship and research opportunities, checking eligibility against a personal profile, and ranking them by fit. Eligibility is time-aware: the current user is a high-school senior, and opportunities are evaluated against their expected status when each one begins (for example, as an incoming undergraduate).

**Intended user:** a single user (the repository owner). It's still being built to production standards.

> ⚠️ **Status: profile intelligence and fit ranking v1 (Milestone 4, in review).** Milestone 3.5 is merged and deployed (Vercel → Render → Neon, [docs/deployment.md](docs/deployment.md)). Log in, keep a private eligibility profile and a Match Profile (skills, courses, projects, interests, location and schedule preferences), sync a broad internship feed and any Greenhouse or Lever company boards you add (internship postings only by default), and browse opportunities in recommended order: eligibility first, then a deterministic fit score with a "Why this match?" breakdown. Review an imported posting's requirements, see eligibility evaluated automatically with plain-language explanations, and track applications. Sync runs only when you ask; there's no scheduler. There is no résumé upload or parsing, no AI, and no automatic requirement extraction. See [PROJECT_STATE.md](PROJECT_STATE.md) for the current state.

## Stack

**Implemented, and provisioned on free plans** ([ADR-004](docs/decisions/ADR-004-technology-stack.md), hosting in [ADR-009](docs/decisions/ADR-009-hosted-deployment-architecture.md)):

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, built as a static client-side app and hosted on Vercel Hobby
- **Backend:** Python, FastAPI, Pydantic, hosted on a Render Free Web Service
- **Database:** Neon PostgreSQL Free, accessed with SQLAlchemy 2.x, Alembic, and psycopg
- **CI / scheduling:** GitHub Actions (included free usage)
- **Testing:** Pytest, Vitest, Playwright

**Hard constraint:** $0/month, and no payment method required for any required service.

Opportunity sourcing and profile ingestion strategy: [ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md).

## Local Development

Requires Node.js 24, Python 3.12+, and Docker (for the local PostgreSQL 18).

```bash
docker compose up -d                 # local-only PostgreSQL, data in a Docker volume

# Backend (first terminal): http://localhost:8000
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
python -m app.cli create-owner --username <your-username>   # password via a hidden prompt
uvicorn app.main:app --reload

# Frontend (second terminal): http://localhost:5173, proxies /api to the backend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and log in. There's no sign-up page: the owner account exists only through the CLI. Open **Sources** and choose **Sync now** on the built-in discovery feed to import current postings (or run `python -m app.cli sync-sources`). Lint, typecheck, test, end-to-end, and build commands are in [docs/development.md](docs/development.md).

## Public Repository

This repository contains application source code only. Personal résumé, profile, application, and credential data must never be committed. See [CLAUDE.md](CLAUDE.md#public-repository-safety).

Imported postings come from public sources listed with their licensing and attribution in [docs/sources.md](docs/sources.md). The repository never contains downloaded postings.

The running app is private: one owner account, created from the command line, with Argon2id password hashing, server-side sessions in an HttpOnly cookie, and CSRF protection ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md)). Your profile, opportunities, and application notes live only in your database. Tests and CI use synthetic data and throwaway databases.

## Environment

The backend's example file is [`backend/.env.example`](backend/.env.example) (it points at the local Compose database). The frontend needs no variables. Never commit real values.

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
| [docs/scoring.md](docs/scoring.md) | Fit scoring v1: components, weights, coverage, ranking |
| [docs/sources.md](docs/sources.md) | Opportunity source registry |
| [docs/operations.md](docs/operations.md) | Runtime operations and monitoring |
| [docs/decisions/](docs/decisions/) | Architecture decision records |
