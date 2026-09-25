# ADR-004: React/Vite Frontend and Python/FastAPI Backend on Zero-Cost Infrastructure

Status: Accepted

Date: 2026-09-24

> This ADR **selects** the stack and hosting. Nothing listed here is **provisioned** (no accounts, projects, or databases created) or **implemented** (no code, dependencies, or migrations) yet. See [PROJECT_STATE.md](../../PROJECT_STATE.md) for the current state.

## Context

The Personal Internship Finder is a private, single-user tool. It needs:

- a web UI for the dashboard, opportunity browsing, filters, the profile, application tracking, and import/review screens
- a backend that runs ingestion (HTTP APIs, ATS feeds, HTML parsing), normalization, deduplication, deterministic eligibility, fit scoring, and ranking
- persistent relational storage
- scheduled jobs (discovery, refreshes, stale checks)
- room for future data work: NLP, embeddings, local models, browser automation, ranking experiments, research-agent workflows

It has a hard operating constraint:

```text
$0/month
No payment method required
```

Required services must stay usable without a credit card, payment information, a paid subscription, automatic usage-based billing, or paid overages. When a free-tier limit is exceeded, the preferred behavior is to **pause, throttle, fail, or defer** processing, never to incur charges.

It doesn't need SSR, server components, server actions, or SEO-oriented rendering. It's a private tool behind a login, not a public content site.

## Decision

### Summary

| Layer | Selected | Hosting / service |
|---|---|---|
| Frontend | React, TypeScript (strict), Vite, Tailwind CSS | Vercel Hobby (static assets) |
| Frontend validation | Zod, where runtime validation is useful | — |
| Backend | Python, FastAPI, Pydantic | Render Free Web Service |
| Database | PostgreSQL | Neon Free |
| DB access | SQLAlchemy 2.x, Alembic, psycopg | — |
| Backend tests | Pytest | — |
| Frontend tests | Vitest, React Testing Library where useful | — |
| End-to-end tests | Playwright | — |
| Python quality | Ruff, Pyright (or equivalent), modern type hints | — |
| TypeScript quality | strict mode, ESLint, Prettier | — |
| Repository / CI | GitHub, GitHub Actions (included free usage only) | GitHub |
| Scheduling | GitHub Actions scheduled workflows (later: self-hosted runner) | GitHub |
| Object storage | None initially | — |
| Notifications | In-app/dashboard only initially | — |
| AI | Optional; no paid API required ([ADR-003](ADR-003-ai-as-enrichment.md)) | — |

Target runtime shape:

```text
Browser
   ↓
React / TypeScript (static, built by Vite, served by Vercel)
   ↓  HTTPS / JSON
FastAPI (Render)
   ↓
PostgreSQL (Neon)
```

Not:

```text
Browser → Next.js server → FastAPI server → PostgreSQL
```

There is exactly one backend runtime, and it's Python.

### Frontend

React + TypeScript + Vite + Tailwind CSS, built as a **client-side application** and deployed as static assets.

Responsibilities: dashboard, opportunity browsing, filters, profile UI, application tracking, import/review screens, and frontend interactions.

Core business logic (eligibility, scoring, ranking, normalization, deduplication) lives in the backend. It must not exist only inside frontend components. Zod is used where runtime validation helps (for example, checking API responses or form input), but backend validation is authoritative, and complicated business rules aren't duplicated across frontend and backend.

### Why Vite

Vite is the frontend dev server and build tool. It provides:

- fast local development
- TypeScript support
- React integration
- static production builds
- simple deployment to Vercel (or any static host)
- minimal server-side complexity

### Why not Next.js (initially)

Next.js is a strong framework, but its main advantages (SSR, server components, server actions, SEO-oriented rendering, a Node server runtime) solve problems this project doesn't have. Adopting it alongside a Python backend would add a second server runtime to deploy, secure, and keep within free-tier limits, and would create a tempting second place for business logic. A static Vite build keeps the frontend a plain client of the FastAPI API.

If a real need for SSR or a server-side frontend runtime appears, revisit this through a new ADR.

### Backend

Python + FastAPI + Pydantic.

Python is intentionally chosen over TypeScript for the backend. Expected backend workloads include job/internship crawling, HTTP API ingestion, HTML parsing, normalization, data processing, recommendation experiments, NLP, embeddings, local AI models, browser automation, ranking experiments, research-agent workflows, batch jobs, and data analysis. Python's ecosystem is stronger for these.

FastAPI provides typed APIs, async support, OpenAPI generation, Pydantic integration, and a clean frontend/backend boundary.

Pydantic validates, at minimum:

- API requests and responses
- normalized opportunities
- source adapter output
- imported profile data
- configuration
- future AI-generated structured output

External data is untrusted.

The two-language split (TypeScript frontend, Python backend) is intentional. Don't convert the backend to TypeScript solely for language consistency.

### Database

Neon PostgreSQL (Free plan), accessed with SQLAlchemy 2.x, Alembic, and psycopg.

- It's real, standard PostgreSQL, so it's portable to any other Postgres host.
- It fits the Python/Postgres ecosystem and personal-scale data.
- It doesn't require a payment method for the selected free usage (verify at provisioning time).
- All production schema changes go through Alembic migrations.
- Avoid unnecessary ORM abstractions. Raw SQL is acceptable where it's clearer or more efficient.
- Neon-specific features must not be required by application code, so the database stays swappable for any Postgres.

### Frontend hosting

Vercel Hobby, serving the Vite build as static assets.

- Simple GitHub integration, preview deployments, and static hosting that suits a React/Vite app.
- Hobby doesn't require a payment method and is intended for personal, non-commercial use, which matches this project.
- Don't depend on paid Vercel features, Vercel serverless/edge functions, or Vercel-specific storage. The frontend must remain deployable to any static host.

### Backend hosting

Render Free Web Service.

- The service may sleep when idle. Cold starts are acceptable.
- The local filesystem isn't durable. Persistent state must never depend on Render disk.
- The backend must tolerate restarts and cold starts (stateless processes, configuration from environment variables).
- Don't use paid Render services or paid add-ons.
- Deployment must stay replaceable (for example, a standard Python/ASGI process that could run on another host) without rewriting the application.

### CI

GitHub Actions within included free usage. CI should eventually run:

- Backend: Ruff, type checks, Pytest
- Frontend: lint, TypeScript check, Vitest, build
- Repository: migration validation and docs checks where practical

Don't enable paid runner usage (larger runners, paid minutes, or a spending limit above $0). If hosted-runner limits become a problem, prefer a self-hosted runner.

### Scheduling

GitHub Actions scheduled workflows, or later a self-hosted runner. No paid scheduler.

Scheduled workflows may eventually handle opportunity discovery, ATS refreshes, stale listing checks, deadline refreshes, ranking recalculation, and source health checks.

Workflow YAML only **orchestrates**. It invokes Python application commands (for example, a CLI entry point in the backend package). The core logic stays in reusable Python modules that are also testable and runnable locally. A scheduled job can run the Python command directly in the runner against Neon, so it doesn't need to wake the Render service.

### Testing

- Backend: Pytest
- Frontend: Vitest, plus React Testing Library where useful
- End-to-end: Playwright

Critical business logic must be testable outside the UI.

### Object storage and notifications

No external object storage initially (no S3, R2, Firebase Storage, or paid storage). Add one only when a real use case appears, via a new ADR if it requires payment information.

Notifications start in the application/dashboard. No email/SMS infrastructure as a core dependency, and no SendGrid, Resend, Twilio, or paid notification services without explicit approval.

### AI

AI stays optional ([ADR-003](ADR-003-ai-as-enrichment.md)). The core application must work without the OpenAI API, Anthropic API, paid Gemini API, paid embedding APIs, or paid vector databases. Initial eligibility and scoring use deterministic rules, structured profile data, and keyword/semantic logic that doesn't require paid APIs. Future enrichment may use local models (for example, Ollama), optional manually triggered inference, free provider allocations, or pluggable provider adapters.

### Zero-cost / no-payment constraint

This constraint is binding on all **required** services:

- No required service may need a credit card, payment information, a paid plan, automatic usage-based billing, or paid overages.
- When a free-tier limit is hit, the system should pause, throttle, fail visibly, or defer work. It must not incur charges.
- Any future **required** dependency that needs payment information, can automatically generate charges, or requires a paid plan must be approved through a **new ADR before adoption**.
- Free-tier terms change. Each provisioning task must confirm that the service still requires no payment method before creating an account or project, and stop and report if it does.

### Portability

Every hosted piece has a standard fallback:

| Piece | Standard form | Replaceable by |
|---|---|---|
| Frontend | Static files from `vite build` | Any static host |
| Backend | Python ASGI app | Any host that runs a Python process or container |
| Database | Standard PostgreSQL + Alembic migrations | Any PostgreSQL |
| Scheduling | Python CLI commands | Self-hosted runner, cron, or any job runner |

If Vercel, Render, or Neon materially changes its free/no-payment policy, the project should move without rewriting application code.

## Consequences

- Two languages and two toolchains (Node for the frontend, Python for the backend), each with its own lint, typecheck, test, and build commands.
- API contracts cross a language boundary. FastAPI's OpenAPI output is the contract. Frontend types may be generated from it or maintained by hand, but backend Pydantic models are authoritative.
- CORS must be configured on the backend for the Vercel origin.
- Render cold starts add latency to the first request after idle. The UI should show a loading state rather than treat slow first responses as failures.
- Free-tier limits (Neon compute/storage, Render hours, GitHub Actions minutes) cap throughput. Jobs must be designed to work within them and to stop rather than escalate.
- No SSR: the app isn't indexable by search engines, which is fine for a private tool.
- Supabase-specific guidance (Supabase Auth, RLS through Supabase) no longer applies by default. Authorization is enforced in the FastAPI backend. Postgres RLS remains available if it's needed later.

## Alternatives Considered

These alternatives aren't worse in general. They fit this project's current requirements less well.

- **Full TypeScript stack (Node/TS backend).** One language and shared types across the stack is a real advantage. It wasn't selected because the expected backend workloads (crawling, parsing, NLP, embeddings, local models, data analysis) have a stronger ecosystem in Python.
- **Next.js.** Excellent for SSR, SEO, and full-stack TypeScript apps. It wasn't selected because the project needs none of SSR, server components, server actions, or SEO rendering, and adding it would introduce a second backend runtime next to FastAPI.
- **Cloudflare-hosted frontend (Pages/Workers static assets).** A capable static host with a generous free tier, and a valid fallback since the Vite build is portable. Vercel was chosen for its simple GitHub integration and preview deployments. Either would work.
- **Supabase.** Offers Postgres plus auth, storage, and APIs in one product. It wasn't selected because this project's backend is a separate FastAPI service, so most of Supabase's value would go unused or would compete with the backend as a second place for logic. Free projects can also be paused for inactivity. Neon provides plain Postgres, which is what the backend needs.
- **Cloudflare D1.** A SQLite-based serverless database, cheap and fast at the edge. It wasn't selected because it isn't PostgreSQL, fits best with Workers rather than a Python/SQLAlchemy/Alembic backend, and would reduce portability to standard Postgres.
- **Render Postgres.** Convenient next to a Render web service. It wasn't selected because Render's free Postgres instances are time-limited, and a personal tool needs durable storage it can rely on without a paid upgrade. Keeping the database on a separate provider also keeps the backend host swappable.
