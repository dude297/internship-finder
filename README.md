# Personal Internship Finder

A private tool for finding internship and research opportunities, checking eligibility against a personal profile, and ranking them by fit. Eligibility is time-aware: the current user is a high-school senior, and opportunities are evaluated against their expected status when each one begins (for example, as an incoming undergraduate).

**Intended user:** a single user (the repository owner). It's still being built to production standards.

> ⚠️ **Status: pre-implementation.** Only engineering documentation exists. The capabilities described in `docs/` are **planned**, not implemented. See [PROJECT_STATE.md](PROJECT_STATE.md) for the current state.

## Stack

**Selected, not yet provisioned or implemented** ([ADR-004](docs/decisions/ADR-004-technology-stack.md)):

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, built as a static client-side app and hosted on Vercel Hobby
- **Backend:** Python, FastAPI, Pydantic, hosted on a Render Free Web Service
- **Database:** Neon PostgreSQL Free, accessed with SQLAlchemy 2.x, Alembic, and psycopg
- **CI / scheduling:** GitHub Actions (included free usage)
- **Testing:** Pytest, Vitest, Playwright

**Hard constraint:** $0/month, and no payment method required for any required service.

Opportunity sourcing and profile ingestion strategy: [ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md).

## Local Development

No application code, package manifest, or scripts exist yet, so there is nothing to install, run, or test. The next milestone is the application scaffold. See [docs/development.md](docs/development.md). It will list real commands once they exist.

## Environment

No environment variables are required yet. [`.env.example`](.env.example) will list placeholders as features add them. Never commit real values.

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
