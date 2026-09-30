# Architecture

## Current

Milestones 0–4 are merged. Milestone 4 (Match Profile, fit scoring v1, eligibility-first ranking, internships-only board scope, [ADR-010](decisions/ADR-010-fit-scoring-v1.md)) is released from `main`. Milestone 3.5 (hosted deployment foundation, [ADR-009](decisions/ADR-009-hosted-deployment-architecture.md)) is deployed from `main`: Vercel (static build + same-origin `/api` rewrite) → Render (FastAPI) → Neon (PostgreSQL). No schedulers. The local topology below is unchanged; the hosted one is in [deployment.md](deployment.md#topology).

```text
Browser ── same origin ──► Vite dev server (localhost:5173)
   │  HttpOnly session cookie      │  /api/* proxied
   │  X-CSRF-Token on mutations    ▼
   │                         FastAPI (localhost:8000)            python -m app.cli sync-source(s)
   │                           ├─ public:  GET /api/health, POST /api/auth/login, GET /api/auth/session
   │                           └─ private (require_owner): logout, profile, opportunities, tracking,
   │                                  │                    sources + manual sync
   │                                  │         ┌──────────────────────────────┘
   │                                  │         ▼
   │                                  │   ingestion pipeline ── HTTPS GET, allowlisted hosts only ──►
   │                                  │         │                 zshah101.github.io (discovery feed)
   │                                  ▼         ▼                 boards-api.greenhouse.io
   └───────────────────────── PostgreSQL 18 (Docker Compose)      api.lever.co / api.eu.lever.co
```

### Backend (`backend/app/`)

| Layer | Location | Responsibility |
|---|---|---|
| Route handlers | `api/` (`auth.py`, `profile.py`, `opportunities.py`, `sources.py`, `health.py`) | Thin: parse the request, call a service, commit once, shape the response (sync endpoints delegate their commits to the pipeline) |
| Authorization boundary | `api/deps.py` (`require_owner`) | Session cookie → `401`; unsafe method without a valid CSRF header → `403`. Mounted once on the parent router of every private route (`main.py`) |
| API schemas | `schemas/` | Pydantic request/response models (the HTTP contract), ISO country validation. Response models don't reuse request validators, so any stored row can be read back |
| Services | `services/` (`auth.py`, `profile.py`, `match_profile.py`, `opportunities.py`, `sources.py`, `discovery.py`) | Domain workflows: sessions, profile save + re-evaluation, the Match Profile (manual facts + fit preferences, one atomic save), opportunity/requirement/provenance writes, evaluation, tracking, the source registry (including board scope), and the paginated/filtered discovery query with the recommended (eligibility-first) order. They flush but never commit |
| Ingestion | `ingestion/` (`http.py`, `adapters/`, `normalize.py`, `pipeline.py`) | [ADR-008](decisions/ADR-008-opportunity-ingestion-and-deduplication.md): the only network client (allowlisted HTTPS hosts, size/time/retry limits), adapters that build URLs from hard-coded hosts and normalize items (no database access), and the shared pipeline that applies the source's scope, dedupes, persists, evaluates, closes, and records runs |
| Persistence helpers | `repositories.py` | Load the profile/opportunity, build the evaluation context (eligibility inputs + fit profile input from manual/verified facts), evaluate eligibility and fit together and save (forced, only when a fingerprint changed, or as one batched catalog pass), latest evaluation |
| Domain | `profile/education.py`, `opportunities/eligibility/`, `opportunities/scoring/` | Pure: temporal education resolver, eligibility rules v1 (unchanged since Milestone 1), and fit scoring v1 (`config.py` holds every weight/threshold/alias; `text.py` the lexical matcher; `engine.py` the six components). Scoring never reads eligibility, and adapters never score |
| ORM | `models/` | Tables ([data-model.md](data-model.md)) |
| CLI | `cli.py` | `create-owner`, `set-password` (the only way to create or change credentials); `sync-sources`, `sync-source` (the same pipeline as the API) |

**Transactions.** One database session per request (`db/session.py`). The handler commits once after its service call; if anything raises first, the session closes and everything is rolled back. So "opportunity + manual source record + requirements + evaluation" and "profile update + every resulting re-evaluation" are each atomic. Source sync is the deliberate exception ([ADR-008 §4](decisions/ADR-008-opportunity-ingestion-and-deduplication.md#4-run-history-and-partial-success)): it commits a `running` run first, fetches outside any transaction, writes each item in its own savepoint, and commits the results with the finished run, so one bad item can't discard the rest.

**Ingestion.** `fetch → validate → normalize → identify → upsert → evaluate → close → run summary`. Identity is exact only: same source + external ID, then deterministic identifiers (`zshah`, `greenhouse`, `lever`, canonical `url`). Identifiers that point at two opportunities are an error, never a merge. Only a complete successful snapshot closes postings it no longer lists; closed postings are kept (with their tracking) and reopen if they return. Opportunities the owner has edited (`manually_curated_at`) keep their canonical fields and requirements across syncs. Imported opportunities start `unassessed`.

**Errors.** FastAPI's standard shape: `{"detail": "message"}` or, for `422`, `{"detail": [{"loc", "msg", "type"}]}` without the echoed input. Integrity conflicts → `409`; anything unexpected → `500 {"detail": "Internal server error."}` (logged server-side). Details: [ADR-007 §9](decisions/ADR-007-single-user-auth-and-private-api.md#9-api-error-model).

**Automatic evaluation.** Every evaluation row carries eligibility and fit. Creating or updating an opportunity (by hand or by a sync) appends one when a profile exists and the eligibility or fit inputs changed, compared by two SHA-256 fingerprints, so repeated syncs don't grow the history ([ADR-008 §9](decisions/ADR-008-opportunity-ingestion-and-deduplication.md#9-evaluation-without-history-explosion), [ADR-010 §8](decisions/ADR-010-fit-scoring-v1.md#8-persistence-and-fingerprints)). Without a profile, the opportunity is saved and reported as not evaluated. Saving the profile with a changed eligibility field (the fields of `ProfileInput`: education timeline, date of birth, citizenships), or saving the Match Profile, runs one synchronous catalog pass in the same transaction: latest fingerprints in one query, opportunities in keyset batches of 200, unchanged pairs skipped ([operations.md](operations.md#evaluation-history-and-re-evaluation-implemented-not-scheduled) has timings). `POST /api/opportunities/{id}/evaluate` appends one on demand. Application tracking never triggers evaluation.

### Frontend (`frontend/src/`)

| Area | Location |
|---|---|
| Routing | `App.tsx` (react-router): `/login`, `/profile` (Eligibility Profile), `/profile/match` (Match Profile), `/opportunities` (paginated; filters and sort in the URL query, recommended by default), `/opportunities/new`, `/opportunities/:id`, `/opportunities/:id/edit` (also the requirement review for imported opportunities), `/sources` |
| Auth state | `auth/` context from `GET /api/auth/session`. `RequireAuth` redirects to `/login` (a UX convenience; the API enforces access). An auth generation counter drops a session check that resolves after a newer login/logout/session loss. Logout clears local state only once the server confirms it (`204`, or `401` = already invalid); otherwise the user stays signed in and sees an error ([ADR-007 §3](decisions/ADR-007-single-user-auth-and-private-api.md#3-opaque-server-side-sessions)) |
| API client | `api/client.ts` (the only `fetch` caller): relative `/api` URLs, same-origin credentials, Zod validation (`api/schemas.ts`), central `401` handling, `X-CSRF-Token` on mutations, CSRF token in memory only |
| Pages / components | `pages/`, `components/` (presentation only) |
| Wording | `lib/labels.ts`, `lib/eligibility.ts` rephrase stored rule results in plain language. They never re-evaluate. `components/WhyThisMatch.tsx` shows the stored fit breakdown; the frontend never computes a score |

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

profiles (fit preferences) + accepted profile_facts ─┐
opportunities ───────────────────────────────────────┴► score_fit ──► same evaluation row
                                                                              (fit_score, score_breakdown)
```

Ranking (`sort=recommended`): eligibility bucket, then `fit_score` (none last), then posted date, first seen, and ID.

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

ADR-007's same-origin constraint is met by Vercel rewriting `/api/*` to Render before the SPA fallback, so the session cookie is host-only on the Vercel host. `Secure` cookies and proxy-aware login throttling are in [ADR-009](decisions/ADR-009-hosted-deployment-architecture.md).

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

Milestone 3 implements the sources, normalize/validate/dedupe, and persistence stages, run manually (UI, API, CLI). Scheduled collection is **not** implemented: the database is local, and a GitHub-hosted runner can't reach it. Once a hosted database exists, scheduled workflows run Python application commands (the same backend package, e.g. `python -m app.cli sync-sources`) against the database. The workflow YAML only orchestrates, and core logic lives in reusable Python modules. Sources are layered: public feeds → ATS APIs → early-college/research programs → custom career pages → browser automation ([ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md)).

### Profile Flow (Milestone 5 for résumés; other sources future)

```text
Résumé (plain text or text-based PDF, ≤ 2 MB)
                     ↓
  content sniffing ─► profile_source_artifacts (original bytes, PostgreSQL, immutable)
                     ↓
  deterministic parser (PDF text in a time- and memory-limited child process)
                     ↓
  profile_facts, review_state = pending   (with provenance; never scored)
                     ↓
  owner review on "Imported Profile": accept / edit + accept / reject, one batch
                     ↓
  accepted facts ─► one catalog pass ─► Fit Scoring v1
```

Imported facts never write the canonical `profiles` row, so eligibility still reads only what the owner entered on the Eligibility Profile ([ADR-011](decisions/ADR-011-profile-source-ingestion-and-review.md)). Transcripts, course lists, GitHub, DOCX, OCR, and optional AI enrichment remain future work. Original source documents are kept unchanged, and extracted facts are stored separately with provenance ([ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md)).

Everything in this flow is private runtime data (database or gitignored local storage), never repository content. The public repository holds only code, schemas, migrations, synthetic fixtures, and generic docs ([ENGINEERING_GUIDELINES.md §16](../ENGINEERING_GUIDELINES.md#public-code--private-data-boundary)).

### Components (target; the first four exist since Milestone 3)

| Component | Responsibility | Reference |
|---|---|---|
| Source adapters | Fetch raw records from one source and normalize them. No DB writes, scoring, eligibility, or dedupe (implemented: discovery feed, Greenhouse, Lever) | [sources.md](sources.md), [ADR-002](decisions/ADR-002-shared-ingestion-pipeline.md), [ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md) |
| Normalization | Map raw records to a common opportunity shape; validate with Pydantic | [ADR-002](decisions/ADR-002-shared-ingestion-pipeline.md) |
| Deduplication | Match by stable external ID, then by exact deterministic identifiers; no fuzzy matching ([ADR-008](decisions/ADR-008-opportunity-ingestion-and-deduplication.md)) | [sources.md](sources.md) |
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
- **Recurring discovery:** scheduled source runs (for example GitHub Actions calling `python -m app.cli sync-sources`) once the database is hosted. Not possible against the local database.
- **Alerts:** in-app notifications for new high-fit eligible opportunities. No email/SMS services initially.
- **Personalized learning:** tuning ranking from user feedback.

## Maintenance

Update this file when components move from Planned to Current, or when architecture changes. Record significant decisions as ADRs.
