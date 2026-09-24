# Architecture

## Current

Nothing is implemented. The repository contains documentation only. No stack, application code, database, or deployment exists.

## Planned

Everything below is the **target** architecture. None of it exists until the code does, and [PROJECT_STATE.md](../PROJECT_STATE.md) records what has been built.

### Target Pipeline

```text
Opportunity Sources
        ↓
Source Adapters
        ↓
Normalization
        ↓
Deduplication
        ↓
Shared Ingestion Pipeline
        ↓
Opportunity Database
        ↓
Eligibility Engine
        ↓
Fit Scoring
        ↓
Ranking
        ↓
Dashboard
```

### Components (planned)

| Component | Responsibility | Reference |
|---|---|---|
| Source adapters | Fetch raw records from one source; no DB writes | [sources.md](sources.md), [ADR-002](decisions/ADR-002-shared-ingestion-pipeline.md) |
| Normalization | Map raw records to a common opportunity shape; validate | [ADR-002](decisions/ADR-002-shared-ingestion-pipeline.md) |
| Deduplication | Match by stable external ID, then by fallback heuristics | [sources.md](sources.md) |
| Shared ingestion pipeline | Only path that persists opportunities; produces run summaries | [operations.md](operations.md) |
| Opportunity database | Stores opportunities, profile, evaluations, application state | [data-model.md](data-model.md) |
| Eligibility engine | Deterministic `eligible` / `ineligible` / `needs_verification` | [eligibility.md](eligibility.md), [ADR-001](decisions/ADR-001-separate-eligibility-and-fit.md) |
| Fit scoring | Versioned, weighted personal fit score | [scoring.md](scoring.md) |
| Ranking | Orders by eligibility first, then fit | [scoring.md](scoring.md) |
| Dashboard | Presentation only; no business rules | — |

### Future Layers

These are future capabilities. They stay unimplemented until built and recorded in `PROJECT_STATE.md`:

- **AI enrichment:** requirement extraction, summarization, explanations. Enrichment only ([ADR-003](decisions/ADR-003-ai-as-enrichment.md)).
- **Recurring discovery:** scheduled source runs.
- **Alerts:** notifications for new high-fit eligible opportunities.
- **Application tracking:** the user's application status per opportunity.
- **Personalized learning:** tuning ranking from user feedback.

## Maintenance

Update this file when components move from Planned to Current, or when architecture changes. Record significant decisions as ADRs.
