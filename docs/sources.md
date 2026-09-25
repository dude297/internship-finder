# Opportunity Sources

Every source feeds the shared ingestion pipeline ([ADR-002](decisions/ADR-002-shared-ingestion-pipeline.md)). No source writes to the database directly. The source strategy is layered, not crawler-only ([ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md)).

## Source Layers

| Priority | Layer | Approach |
|---|---|---|
| 1 | Existing public structured feeds | Consume where legally and technically appropriate (license/terms checked) |
| 2 | Direct ATS sources | Greenhouse, Lever, Ashby, other structured ATS APIs |
| 3 | High-school / early-college specific | University summer research and labs, research internships, fellowships, government and nonprofit STEM programs, startup internships, hackathons, technical summer programs, accelerators, scholarships with technical/project components, incoming-freshman and first-year undergraduate programs |
| 4 | Custom career pages | HTML parsing where needed |
| 5 | Browser automation | Only when simpler structured approaches are unavailable |

Priority 3 is strategically the most important layer for this user, even though it's harder to automate.

## Source Registry

| Source | Layer | Type | Method | Status | Refresh | Notes |
|---|---|---|---|---|---|---|
| Public internship feeds | 1 | Structured dataset | JSON/feed (TBD) | Planned | TBD | Candidates under [Research References](#research-references). License/terms must be checked first |
| Greenhouse | 2 | ATS job boards | Public job board API (TBD) | Planned | TBD | Per-company board tokens; stable job IDs expected |
| Lever | 2 | ATS job boards | Public postings API (TBD) | Planned | TBD | Per-company slugs; stable posting IDs expected |
| Ashby | 2 | ATS job boards | Public job board API (TBD) | Planned | TBD | Per-company boards; stable IDs expected |
| University/research programs | 3 | Program pages | TBD (curated list + parsing) | Planned | TBD | Often seasonal and deadline-driven; start dates matter for time-aware eligibility |
| Government / nonprofit STEM programs, fellowships | 3 | Program pages | TBD | Planned | TBD | Often high-school or incoming-freshman eligible |
| Selected company career pages | 4 | Company sites | HTML parsing (TBD) | Planned | TBD | Stable IDs may be missing; needs fallback dedupe |
| Manual import | — | User-entered | Manual entry / file import (TBD) | Planned | On demand | Validated like any other source |

No source is implemented. Scheduled refreshes will run as GitHub Actions workflows that invoke Python commands ([ADR-004](decisions/ADR-004-technology-stack.md)).

## Adapter Boundary

Conceptual interface (Python; final shape decided at implementation):

```python
class OpportunitySource:
    async def fetch(self) -> list[RawOpportunity]: ...
    def normalize(self, raw: RawOpportunity) -> NormalizedOpportunity: ...
```

Transport varies by source. The shared boundary starts after `fetch`. Adapters don't implement scoring, eligibility, schema, or deduplication.

## Required Definition per Source

Before a source moves to **Implemented**, document:

- **Source name:** a unique identifier used in records and logs
- **Source type / layer:** feed, ATS, program page, company site, manual, etc.
- **Ingestion method:** API, feed, HTML parse, browser automation, manual
- **License / terms:** for feeds and scraped sites, whether use is permitted
- **Stable ID behavior:** which external ID is used, or how a surrogate is derived when none exists
- **Dates captured:** start date, deadline (needed for time-aware eligibility)
- **Refresh cadence:** how often it runs
- **Failure behavior:** timeouts, rate limits, malformed records, partial results
- **Deduplication strategy:** external ID first, then fallback matching (e.g. normalized org + title + URL)

## Research References

These projects are **research references only**. None is a dependency, and core architecture must not be coupled to any of them. Reuse follows the open-source policy in [ADR-005 §9](decisions/ADR-005-source-and-profile-ingestion-strategy.md#9-open-source-reuse-policy): inspect the license, check compatibility, record attribution, check copyleft obligations, and document any reuse before copying code.

| Repository | License | Relevant ideas | Allowed use |
|---|---|---|---|
| [`pleasedodisturb/kestrel`](https://github.com/pleasedodisturb/kestrel) | AGPL-3.0 | FastAPI backend, React frontend, profile-based job scoring, application pipeline tracking, source registry, AI-provider abstraction, scoring evaluation harness, extensive tests | Architectural reference only. **No code copying** unless licensing is separately reviewed and explicitly approved |
| [`zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships`](https://github.com/zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships) | Not yet verified | Large ATS source registry, automated collection, structured JSON output, skill extraction, citizenship/visa indicators, posting dates, dedupe, recurring GitHub Actions refresh | Research reference; possible source seed list or feed adapter (layer 1) if license/terms permit |
| [`SuryaHarikrishnan/2027-internship-tracker`](https://github.com/SuryaHarikrishnan/2027-internship-tracker) | Not yet verified | Large listings, category organization, GitHub Actions refresh, application tracking, ranking/freshness concepts | Reference or optional feed adapter (layer 1) only, not a foundation |

## Maintenance

Update this registry whenever a source is added, removed, or changes status, and update [PROJECT_STATE.md](../PROJECT_STATE.md) → Active Opportunity Sources to match.
