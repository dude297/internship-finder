# Architecture

## Current

Milestones 0 and 1 are merged. Milestone 2 (private single-user workflow MVP) is implemented on `feature/private-workflow-mvp`, awaiting review. The application runs **locally only**. Nothing is **provisioned** (no accounts, hosted databases, or deployments).

```text
Browser ── same origin ──► Vite dev server (localhost:5173)
   │  HttpOnly session cookie      │  /api/* proxied
   │  X-CSRF-Token on mutations    ▼
   │                         FastAPI (localhost:8000)
   │                           ├─ public:  GET /api/health, POST /api/auth/login, GET /api/auth/session
   │                           └─ private (require_owner): logout, profile, opportunities, tracking
   │                                  │
   │                                  ▼
   └───────────────────────── PostgreSQL 18 (Docker Compose, local only)
```

### Backend (`backend/app/`)

| Layer | Location | Responsibility |
|---|---|---|
| Route handlers | `api/` (`auth.py`, `profile.py`, `opportunities.py`, `health.py`) | Thin: parse the request, call a service, commit once, shape the response |
| Authorization boundary | `api/deps.py` (`require_owner`) | Session cookie → `401`; unsafe method without a valid CSRF header → `403`. Mounted once on the parent router of every private route (`main.py`) |
| API schemas | `schemas/` | Pydantic request/response models (the HTTP contract), ISO country validation. Response models don't reuse request validators, so any stored row can be read back |
| Services | `services/` (`auth.py`, `profile.py`, `opportunities.py`) | Domain workflows: sessions, profile save + re-evaluation, opportunity/requirement/provenance writes, evaluation, tracking. They flush but never commit |
| Persistence helpers | `repositories.py` | Load the profile/opportunity, evaluate and save, latest evaluation |
| Domain | `profile/education.py`, `opportunities/eligibility/` | Pure: temporal education resolver and eligibility rules v1 (Milestone 1, unchanged) |
| ORM | `models/` | Tables ([data-model.md](data-model.md)) |
| CLI | `cli.py` | `create-owner`, `set-password` (the only way to create or change credentials) |

**Transactions.** One database session per request (`db/session.py`). The handler commits once after its service call; if anything raises first, the session closes and everything is rolled back. So "opportunity + manual source record + requirements + evaluation" and "profile update + every resulting re-evaluation" are each atomic.

**Errors.** FastAPI's standard shape: `{"detail": "message"}` or, for `422`, `{"detail": [{"loc", "msg", "type"}]}` without the echoed input. Integrity conflicts → `409`; anything unexpected → `500 {"detail": "Internal server error."}` (logged server-side). Details: [ADR-007 §9](decisions/ADR-007-single-user-auth-and-private-api.md#9-api-error-model).

**Automatic evaluation.** Creating or updating an opportunity appends an evaluation when a profile exists (otherwise the opportunity is saved and reported as not evaluated). Saving the profile re-evaluates every opportunity, synchronously and in the same transaction, when a field that eligibility reads changed (the fields of `ProfileInput`: education timeline, date of birth, citizenships). `POST /api/opportunities/{id}/evaluate` appends one on demand. Application tracking never triggers evaluation.

### Frontend (`frontend/src/`)

| Area | Location |
|---|---|
| Routing | `App.tsx` (react-router): `/login`, `/profile`, `/opportunities`, `/opportunities/new`, `/opportunities/:id`, `/opportunities/:id/edit` |
| Auth state | `auth/` context from `GET /api/auth/session`. `RequireAuth` redirects to `/login` (a UX convenience; the API enforces access) |
| API client | `api/client.ts` (the only `fetch` caller): relative `/api` URLs, same-origin credentials, Zod validation (`api/schemas.ts`), central `401` handling, `X-CSRF-Token` on mutations, CSRF token in memory only |
| Pages / components | `pages/`, `components/` (presentation only) |
| Wording | `lib/labels.ts`, `lib/eligibility.ts` rephrase stored rule results in plain language. They never re-evaluate |

Nothing is stored in `localStorage`, `sessionStorage`, or IndexedDB.

### Domain data flow (Milestone 1, unchanged)

```text
profiles ──(canonical fields only)──┐
                                    ▼
opportunities + requirements ──► evaluate_eligibility ──► opportunity_evaluations
                                    │                      └─ eligibility_rule_results
profile_sources ─► profile_facts    │ (facts are not read by eligibility)
opportunity_source_records          ▼
                           resolve_education_status
```

### Public/private boundary

The repository holds code, schemas, migrations, synthetic fixtures, and generic docs. The owner's password hash, sessions, profile, opportunities, evaluations, and application notes exist only in the runtime database (locally, the `pgdata` Docker volume). Tests and CI use synthetic data and disposable databases only ([ENGINEERING_GUIDELINES.md §16](../ENGINEERING_GUIDELINES.md#public-code--private-data-boundary)).

## Planned

Everything below is the **target** architecture. None of it exists until the code does, and [PROJECT_STATE.md](../PROJECT_STATE.md) records what has been built.

### Stack (selected, ADR-004)

| Layer | Technology | Hosting |
|---|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS, Zod where useful | Vercel Hobby (static assets) |
| Backend | Python, FastAPI, Pydantic | Render Free Web Service |
| Database | PostgreSQL via SQLAlchemy 2.x, Alembic, psycopg | Neon Free |
| CI / scheduling | GitHub Actions (included free usage) | GitHub |

Constraint: $0/month and no payment method required for any required service.

Runtime shape: one static frontend and one backend runtime.

```text
Browser
   ↓
React / TypeScript (Vite build, Vercel)
   ↓
FastAPI (Render)
   ↓
PostgreSQL (Neon)
```

**Open constraint from ADR-007:** the hosted topology must keep the browser's API access same-origin (for example, the static host rewriting `/api/*` to the backend) or at least same-site. Two unrelated provider subdomains are not an accepted cookie architecture. This, `Secure` cookies, and login rate limiting must be reviewed before any hosted deployment ([deployment.md](deployment.md)).

### Opportunity Flow

```text
                    GitHub
                      │
                GitHub Actions
                      │
           scheduled collection
                      │
                      ▼
              Python / FastAPI
                      │
      ┌───────────────┼────────────────┐
      │               │                │
 Public Feeds     ATS Sources      Web Sources
      │               │                │
      └───────────────┼────────────────┘
                      ↓
                 Normalize
                      ↓
                 Validate
                      ↓
                Deduplicate
                      ↓
               Neon PostgreSQL
                      ↓
                 Eligibility
                      ↓
                Fit Scoring
                      ↓
                  Ranking
                      ↓
                 FastAPI
                      ↓
          React + TypeScript
                      ↓
                    Vite
                      ↓
                   Vercel
```

Scheduled workflows run Python application commands (the same backend package) against the database. The workflow YAML only orchestrates, and core logic lives in reusable Python modules. Sources are layered: public feeds → ATS APIs → early-college/research programs → custom career pages → browser automation ([ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md)).

### Profile Flow (future)

```text
Resume / Coursework / Projects / Preferences
                     ↓
               Profile Parsers
                     ↓
         Structured Profile Facts   (with provenance)
                     ↓
             User Verification
                     ↓
             Canonical Profile
                     ↓
        Eligibility + Recommendation
```

Original source documents are kept unchanged, and extracted facts are stored separately with provenance ([ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md)).

Everything in this flow is private runtime data (database or gitignored local storage), never repository content. The public repository holds only code, schemas, migrations, synthetic fixtures, and generic docs ([ENGINEERING_GUIDELINES.md §16](../ENGINEERING_GUIDELINES.md#public-code--private-data-boundary)).

### Components (planned)

| Component | Responsibility | Reference |
|---|---|---|
| Source adapters | Fetch raw records from one source and normalize them. No DB writes, scoring, eligibility, or dedupe | [sources.md](sources.md), [ADR-002](decisions/ADR-002-shared-ingestion-pipeline.md), [ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md) |
| Normalization | Map raw records to a common opportunity shape; validate with Pydantic | [ADR-002](decisions/ADR-002-shared-ingestion-pipeline.md) |
| Deduplication | Match by stable external ID, then by fallback heuristics | [sources.md](sources.md) |
| Shared ingestion pipeline | Only path that persists opportunities; produces run summaries | [operations.md](operations.md) |
| Opportunity database | Stores opportunities, profile, evaluations, application state | [data-model.md](data-model.md) |
| Profile ingestion | Raw profile sources → parsed facts with provenance → user review → canonical profile | [ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md) |
| Eligibility engine | Deterministic, time-aware `eligible` / `ineligible` / `needs_verification` | [eligibility.md](eligibility.md), [ADR-001](decisions/ADR-001-separate-eligibility-and-fit.md) |
| Fit scoring | Versioned, weighted personal fit score | [scoring.md](scoring.md) |
| Ranking | Orders by eligibility first, then fit | [scoring.md](scoring.md) |
| API | FastAPI; the frontend's only data access path. Single-user auth and same-origin access | [ADR-004](decisions/ADR-004-technology-stack.md), [ADR-007](decisions/ADR-007-single-user-auth-and-private-api.md) |
| Frontend | Presentation and interaction only; no business rules | [ADR-004](decisions/ADR-004-technology-stack.md) |

### Target Repository Structure

This is the approximate target structure. Directories are created when they have real content, not ahead of time.

```text
/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── features/
│   │   ├── pages/
│   │   ├── api/
│   │   ├── lib/
│   │   └── types/
│   └── tests/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── profile/
│   │   │   ├── ingestion/
│   │   │   ├── parsing/
│   │   │   └── inference/
│   │   └── opportunities/
│   │       ├── ingestion/
│   │       ├── normalization/
│   │       ├── deduplication/
│   │       ├── eligibility/
│   │       ├── scoring/
│   │       ├── ranking/
│   │       └── sources/
│   ├── tests/
│   └── alembic/
│
├── docs/
├── .github/
│   └── workflows/
├── README.md
├── CLAUDE.md
├── ENGINEERING_GUIDELINES.md
└── PROJECT_STATE.md
```

### Future Layers

These are future capabilities. They stay unimplemented until built and recorded in `PROJECT_STATE.md`:

- **AI enrichment:** requirement extraction, summarization, explanations, profile fact inference. Optional, enrichment only, and no paid API required ([ADR-003](decisions/ADR-003-ai-as-enrichment.md), [ADR-004](decisions/ADR-004-technology-stack.md)).
- **Recurring discovery:** GitHub Actions scheduled source runs.
- **Alerts:** in-app notifications for new high-fit eligible opportunities. No email/SMS services initially.
- **Personalized learning:** tuning ranking from user feedback.

## Maintenance

Update this file when components move from Planned to Current, or when architecture changes. Record significant decisions as ADRs.
