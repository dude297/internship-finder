# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

- Added public-repository privacy and secret-handling safeguards.
- Milestone 0 development foundation: a React/TypeScript/Vite/Tailwind frontend (`frontend/`) that shows backend health, validated with Zod, and a FastAPI backend (`backend/`) with `GET /api/health`, a SQLAlchemy base, and an empty Alembic environment. Includes ESLint/Prettier/Vitest and Ruff/Pyright/Pytest tooling, plus a GitHub Actions CI workflow.
- Initial engineering documentation framework.
- Repository operating rules (`CLAUDE.md`, `ENGINEERING_GUIDELINES.md`).
- Project-state handoff document (`PROJECT_STATE.md`).
- Architecture decision records (ADR-001, ADR-002, ADR-003).
- ADR-004: technology stack (React/Vite/Tailwind frontend on Vercel Hobby, Python/FastAPI backend on Render Free, Neon PostgreSQL, GitHub Actions) under a $0/month, no-payment-method constraint.
- ADR-005: layered opportunity sources, time-aware eligibility, provenance-aware profile ingestion, and open-source reuse policy.

### Changed

- Topic docs, `ENGINEERING_GUIDELINES.md`, `README.md`, and `PROJECT_STATE.md` updated for ADR-004/ADR-005. The planned eligibility rule ELIG-EDU-001 is now time-aware.
