# Opportunity Sources

Every source feeds the shared ingestion pipeline ([ADR-002](decisions/ADR-002-shared-ingestion-pipeline.md)). No source writes to the database directly.

## Source Registry

| Source | Type | Method | Status | Refresh | Notes |
|---|---|---|---|---|---|
| Greenhouse | ATS job boards | Public job board API (TBD) | Planned | TBD | Per-company board tokens; stable job IDs expected |
| Lever | ATS job boards | Public postings API (TBD) | Planned | TBD | Per-company slugs; stable posting IDs expected |
| Selected company career pages | Company sites | TBD (API or scraping) | Planned | TBD | Stable IDs may be missing; needs fallback dedupe |
| University/research programs | Program pages | TBD | Planned | TBD | Often seasonal; deadline-driven |
| Manual import | User-entered | Manual entry / file import (TBD) | Planned | On demand | Validated like any other source |

No source is implemented.

## Required Definition per Source

Before a source moves to **Implemented**, document:

- **Source name:** a unique identifier used in records and logs
- **Source type:** ATS, company site, program page, manual, etc.
- **Ingestion method:** API, feed, scrape, manual
- **Stable ID behavior:** which external ID is used, or how a surrogate is derived when none exists
- **Refresh cadence:** how often it runs
- **Failure behavior:** timeouts, rate limits, malformed records, partial results
- **Deduplication strategy:** external ID first, then fallback matching (e.g. normalized org + title + URL)

## Maintenance

Update this registry whenever a source is added, removed, or changes status, and update [PROJECT_STATE.md](../PROJECT_STATE.md) → Active Opportunity Sources to match.
