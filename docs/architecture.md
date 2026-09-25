# Architecture

## Current

Milestone 0 (development foundation) is implemented locally. No product features exist. Nothing is **provisioned** (no accounts, databases, or deployments).

```text
Browser → React/Vite (frontend/, localhost:5173)
            ↓ HTTP GET /api/health (VITE_API_BASE_URL)
          FastAPI (backend/, localhost:8000) → {"status": "ok"}
```

- `frontend/src/api/client.ts` is the only place that calls the API. It validates responses with Zod.
- `backend/app/main.py` creates the FastAPI app, with CORS limited to the single `FRONTEND_ORIGIN` and routers mounted under `/api`.
- `backend/app/db/` has the SQLAlchemy declarative `Base` and a lazily created engine/session. No models or tables exist, and the app never connects to a database.
- `backend/alembic/` is an Alembic environment with no migrations yet.

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
| API | FastAPI; the frontend's only data access path | [ADR-004](decisions/ADR-004-technology-stack.md) |
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
- **Application tracking:** the user's application status per opportunity.
- **Personalized learning:** tuning ranking from user feedback.

## Maintenance

Update this file when components move from Planned to Current, or when architecture changes. Record significant decisions as ADRs.
