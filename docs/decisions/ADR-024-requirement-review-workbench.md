# ADR-024: Requirement Review Workbench

Status: Accepted (Milestone 14, on the feature branch; subject to owner review)

Date: 2026-10-06

## Context

Requirement suggestions ([ADR-012](ADR-012-opportunity-requirement-intelligence-and-automation.md) §7) are reviewed one opportunity at a time, on that opportunity's page. Production holds about 558 pending suggestions (`requirements-rules` v3) and none are accepted, so the opportunity-by-opportunity flow is the bottleneck: opening 400 pages to answer a question that is mostly "is this sentence a hard requirement?".

The owner must stay authoritative ([ADR-003](ADR-003-ai-as-enrichment.md), [ADR-012](ADR-012-opportunity-requirement-intelligence-and-automation.md) §7): a suggestion never affects eligibility until the owner accepts it, and nothing may accept on the owner's behalf.

## Decision

### 1. A global queue is a read plus one batch reject; it adds no requirement-write path

- `GET /api/requirement-review/queue` reads pending suggestions across opportunities.
- Accept, Edit + Accept, and single Reject are the **existing** `POST /api/opportunities/{id}/requirement-review` ([ADR-012](ADR-012-opportunity-requirement-intelligence-and-automation.md) §7): same atomic `apply_review`, same row lock, same "link to an equal existing requirement instead of duplicating", same assessment-status rules, same single re-evaluation. The queue UI calls it with one candidate per request.
- `POST /api/requirement-review/reject-batch` takes `{candidate_ids: [...]}` (1 to **100**, unique) and calls the same `apply_review` per opportunity inside **one transaction**: opportunities are locked in a stable (sorted) order, and the whole batch is rolled back if any ID is unknown (404), repeated, or no longer pending (422, re-checked under the lock so a concurrent accept can never be un-accepted by a batch). A per-opportunity chunk is capped at the service's 50-item limit. Rejecting accepts nothing.
- There is **no** accept-all, accept-category, accept-selected, or auto-accept, in the API or the UI. Every acceptance is an explicit action on one suggestion.

Both endpoints sit behind the existing `require_owner` boundary ([ADR-007](ADR-007-single-user-auth-and-private-api.md)); the batch is an unsafe method, so the CSRF header is required.

### 2. What the queue contains

Pending candidates of **visible** opportunities: not hidden ([ADR-017](ADR-017-owner-opportunity-decisions.md)) and open (`discovery.is_open`), the same visibility as the Inbox's "requirements to review" ([ADR-020](ADR-020-action-inbox.md)). Order: opportunity `first_seen_at` newest first, then opportunity ID, then candidate `created_at`, `id`, so one posting's suggestions sit together and the order is stable.

Each item carries the candidate (including the evidence excerpt `source_text`, extractor name and version), the opportunity (title, organization, application URL, first found, assessment status, "posting changed since review", derived freshness per [ADR-015](ADR-015-freshness-requirements-v2-and-independent-discovery.md), the names and kinds of its source records), the opportunity's canonical requirements, and `duplicate_of`: the ID of a canonical requirement with the same **semantic key** (`requirement_key`: type, normalized value, `applies_at`, reference date; [ADR-012](ADR-012-opportunity-requirement-intelligence-and-automation.md) §3), or null. A duplicate is a **warning, not a block**, consistent with the review service, which links an accepted suggestion to the equal existing requirement and never creates a second one. Extraction already drops a pending suggestion once an equal requirement exists, so a duplicate appears only when a requirement was entered after the queue page was read or arrives through an edit.

### 3. Filters map to stored columns only

| Filter | Stored semantics |
|---|---|
| `requirement_type` | `opportunity_requirement_candidates.requirement_type` (the category) |
| `extractor_name`, `extractor_version` | the candidate's extractor columns (the rule *family* and its version) |
| `organization` | case-insensitive contains on `opportunities.organization` (`%` and `_` literal) |
| `source_kind` | an **active** source record whose `ingestion_sources.kind` matches (provider) |
| `opportunity_id` | the candidate's opportunity |
| `posting_changed` | `opportunities.requirements_stale_since IS NOT NULL` |
| `created_since` | `candidate.created_at >= date` (when the suggestion was first proposed) |

Not available because it is not stored: a per-rule ID (the extractor records only its name and version, so "rule family" is the extractor name) and a confidence score (candidates have none; only the canonical `opportunity_requirements.confidence` column exists, which is unused for deterministic suggestions). The UI filters category, extractor version, source type, organization, and "posting changed"; the API also accepts the rest.

### 3a. Paging is bounded

`limit` is 1 to 100 (default 25; the UI asks for 50 and "Load more" raises it to 100), `offset` 0 to 1,000,000. Offset paging is deliberate: the queue shrinks as it is worked, so the UI re-reads from offset 0 after every decision. Keyset paging would add a cursor for no demonstrated need. `today` and `created_since` are bounded to 2000 to 2999 like the Inbox's `today`.

### 4. Progress summary

Always unfiltered, so filters narrow the page and never the progress: `pending_total` (visible pending), `by_type` (the category distribution), the distinct pending `extractor_versions` (filter options), and `accepted_today` / `rejected_today`.

**Reviewed-today is derived, not stored.** There is no review timestamp; the count is reviewed (accepted or rejected) candidates whose `updated_at` is on or after midnight **UTC** of `today`. `updated_at` is also touched by any later write to the row (for example a re-extraction marking a reviewed candidate `is_current = false`), so the figure can overcount such rows and counts decisions made on the opportunity page too. It is labeled "Reviewed today (UTC)" and is progress feedback, not an audit trail. A review log table was not added: no feature needs one.

### 5. Constant statements

The page is one count, one candidate query that eager-loads opportunity, requirements, source records and their sources (`contains_eager` plus `selectinload`, the raw payload and description deferred), the source-health lookups freshness already uses, and three summary queries. The count does not grow with the page or the catalog; `tests/test_requirement_queue.py` asserts the statement count is equal before and after adding 24 more suggestions across 12 opportunities.

### 6. Frontend

A **Review** page at `/requirements` (nav item; the Inbox section links to it). A focused card per suggestion: opportunity, organization, freshness, source and first-found date, the evidence sentence in a `<mark>`, the suggestion's reading and extractor, the opportunity's existing requirements, and the duplicate warning. Actions: Accept, Edit + Accept (the same `RequirementValueFields` and `toCandidateEdit` the opportunity panel uses), Reject, Skip, Previous, Next. Shortcuts `A` `E` `R` `S` `J` `K` are visible on the page and are ignored with a modifier key, on key repeat, and while typing in an input, select or textarea; `Escape` cancels an edit. Skip and navigation are client-side only. A multi-select list offers **Reject selected** behind an explicit confirmation. Progress shows pending total, remaining in the view, reviewed today, and the category distribution, with no streaks or scores.

## Consequences

- The owner can work the 558-suggestion backlog in one place without a new way to write requirements: the same atomic service, locks, evaluation and CSRF rules apply, and the batch is reject-only and all-or-nothing.
- Accepting stays one suggestion at a time by design; a one-keypress accept makes throughput high without removing the owner's decision.
- "Reviewed today" is approximate; an exact count would need a stored review time (a future migration).
- A batch of 100 across many opportunities runs up to 100 per-opportunity transactions' worth of work in one request (a lock, load, and possible evaluation each). That is fine for one owner; a much larger batch would need chunking.
- No migration, no new dependency, no change to extraction, eligibility, or fit.

## Alternatives Considered

- **Accept-all or accept-by-category.** Rejected: it would let a deterministic extractor write eligibility inputs without the owner reading them ([ADR-012](ADR-012-opportunity-requirement-intelligence-and-automation.md) §7, [ADR-003](ADR-003-ai-as-enrichment.md)).
- **A queue-side accept endpoint.** Rejected: a second requirement-write path would have to re-implement the locking, linking, assessment, and evaluation rules.
- **Blocking a duplicate accept.** Rejected: the service already makes it harmless (it links), and a block would diverge from the opportunity page.
- **A review-event table for exact "reviewed today".** Deferred: not needed for the owner's workflow.
- **Keyset paging.** Deferred: see §3a.
