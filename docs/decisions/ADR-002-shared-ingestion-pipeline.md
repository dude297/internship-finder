# ADR-002: Shared Ingestion Pipeline

Status: Accepted

Date: 2026-09-24

## Context

Opportunities will come from many sources (ATS boards, company pages, research programs, manual import). If each collector validated, deduplicated, and wrote to the database on its own, behavior would drift, duplicates would appear across sources, and failures would be hard to observe consistently.

## Decision

All opportunity sources eventually flow through common stages:

- normalization
- validation
- deduplication
- persistence

Source adapters only fetch raw records and map them to the normalized shape. They don't implement their own database behavior. The shared pipeline is the only writer of opportunity records, and it produces a run summary.

## Consequences

- Adding a source means writing an adapter, not a new persistence path.
- Dedupe, validation, and last-seen tracking are applied consistently and tested once.
- The pipeline must tolerate per-source and per-record failures (partial success).
- The normalized opportunity shape becomes a shared contract. Changing it affects all adapters.

## Alternatives Considered

- **Independent collectors, each writing to the DB.** Rejected: duplicated logic, inconsistent dedupe, poor observability.
- **Third-party aggregation service as the only source.** Rejected for now: less control over coverage and eligibility data. It could later be added as one more adapter.
