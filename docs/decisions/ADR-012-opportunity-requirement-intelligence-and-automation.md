# ADR-012: Opportunity Requirement Intelligence and Automation

Status: Accepted

Date: 2026-10-01

## Context

Milestone 5 released 1,055 imported opportunities. Almost all of them are `unassessed`: eligibility can never be better than `needs_verification` until the owner types each posting's hard requirements into the requirements editor ([ELIG-REQ-000](../eligibility.md)). The text of those requirements is usually already in the posting description. Sync is manual (a button or the CLI), and nothing shows when it stopped working. Ashby, a common ATS, isn't supported. Imported Greenhouse postings are always typed `other`. Application deadlines aren't searchable.

Constraints carried forward: deterministic eligibility, separate from fit ([ADR-001](ADR-001-separate-eligibility-and-fit.md)); AI never authoritative ([ADR-003](ADR-003-ai-as-enrichment.md)); $0/month, no new services ([ADR-004](ADR-004-technology-stack.md)); the shared ingestion pipeline is the only writer of imported data ([ADR-002](ADR-002-shared-ingestion-pipeline.md), [ADR-008](ADR-008-opportunity-ingestion-and-deduplication.md)); one Render instance and worker ([ADR-009](ADR-009-hosted-deployment-architecture.md)); extraction proposes, the owner decides ([ADR-011](ADR-011-profile-source-ingestion-and-review.md)).

## Decision

### 1. Pipeline

```text
source posting → deterministic extraction (requirements-rules v1)
  → pending requirement candidates            (no eligibility effect)
  → owner review: accept / edit + accept / reject, one atomic batch
  → canonical OpportunityRequirement rows     (extraction_method = deterministic_parser)
  → existing eligibility engine, evaluated at most once for that opportunity
```

The eligibility engine and its inputs don't change. It reads only `opportunity_requirements` and `requirements_assessment_status`; it never reads candidates.

### 2. Candidate model

`opportunity_requirement_candidates` (migration `e6d1a4b8c2f9`):

| Column | Meaning |
|---|---|
| `opportunity_id` | cascade delete with the opportunity |
| `semantic_key` | §3. `UNIQUE (opportunity_id, semantic_key)` |
| `requirement_type`, `value`, `applies_at`, `reference_date` | the original proposal, in the canonical requirement shapes |
| `source_text` | bounded evidence excerpt (≤ 500 characters), §5 |
| `extractor_name`, `extractor_version` | `requirements-rules`, `1` |
| `review_state` | `pending` / `accepted` / `rejected` |
| `is_current` | the latest extraction of the current posting text proposed it |
| `accepted_requirement_id` | the canonical requirement created on accept; `SET NULL` if the owner deletes it; non-null only when accepted |

An edited accept writes the edited value to the canonical requirement only. The candidate keeps the original proposal, so its identity survives the edit.

Two `opportunities` columns: `requirements_stale_since` (§6) and `requirement_extraction_fingerprint` (§4). Nothing that can be derived is stored: pending counts are aggregated in the list query.

### 3. Semantic identity

`semantic_key` = SHA-256 of canonical JSON (sorted keys, no whitespace) of `requirement_type`, the normalized value, `applies_at`, and `reference_date`. Normalization: education levels sorted and de-duplicated, countries sorted and uppercased, free-text descriptions casefolded with whitespace collapsed. Never row IDs, source-record IDs, array positions, timestamps, or `source_text`. "Applicants must be at least 16 years old." and "Minimum age: 16." produce the same key, so rephrasing a posting neither duplicates an accepted candidate nor resurrects a rejected one. Code: `app/opportunities/requirements/identity.py`.

A proposal whose key equals the key of an existing canonical requirement of the same opportunity (for example one the owner typed by hand) isn't added: it's already represented.

### 4. Extraction input fingerprint

`extraction_input_fingerprint` = SHA-256 of canonical JSON of `title`, `description`, `application_deadline`, `start_date`. Never `updated_at`, `last_seen_at`, IDs, or evaluation data. `requirement_extraction_fingerprint` on the opportunity = SHA-256 of extractor name, version, and that input fingerprint, written by every extraction. The catalog scan (§9) skips opportunities whose stored value equals the current one, so it's idempotent and a new extractor version rescans everything.

### 5. Extractor `requirements-rules` v1

A pure function (`app/opportunities/requirements/extractor.py`): no network, no AI, no clock, no randomness. Input: §4's fields. Output: an ordered tuple of at most 20 proposals, each with a source excerpt of at most 300 characters (the sentence, trimmed). Precision over recall: when unsure, propose nothing.

| Type | Proposed when the text explicitly says | Value |
|---|---|---|
| `minimum_age` | "must be at least N", "minimum age N", "must be N years of age or older", "applicants must be N years of age", with 10 ≤ N ≤ 30 | `{"years": N}` |
| `education` | an explicit, mandatory enrollment level: "must be a high school student", "currently enrolled in high school", "currently enrolled undergraduate students only", "must be enrolled in a graduate program" | `{"levels": [...], "accepts_incoming": b}`; `accepts_incoming` only with explicit "incoming"/"rising"/"entering" language attached to the accepted level |
| `citizenship` | "must be a U.S. citizen", "U.S. citizens only", "U.S. citizenship (is) required" (country names map to ISO codes from a small explicit table) | `{"countries": ["US"]}` |
| `work_authorization` | "must be authorized to work in the United States", "work authorization required", "citizen or permanent resident" | `{"description": <fixed canonical label>}`; always `needs_verification` (ELIG-REQ-001) |
| `other` | sparingly, for explicit hard requirements no evaluator handles (for example a required security clearance) | `{"description": <fixed canonical label>}` |

Never extracted: sentences with preference or hedge words (`preferred`, `nice to have`, `bonus`, `ideal`, `ideally`, `typically`, `most`, `usually`, `encouraged`, `welcome`, `plus`); vague audiences ("young people", "teens", "high-school age"); soft skills ("strong communication", "team player"); "U.S. person" or "citizen or permanent resident" as citizenship (different legal concepts: the latter is a work-authorization proposal). "High school senior" is never turned into an incoming undergraduate. Also skipped (found by the pre-PR adversarial review): any sentence with a negation or upper bound (`not`, `no`, `never`, `don't`, `non-`, `not eligible`, `or younger`, `under 18`), so "No security clearance is required" or "18 years of age or younger" never invert into a requirement; a number that isn't an age ("at least 18 months", "20 hours per week": the age must be followed by "years", the end of the clause, or a date phrase); any citizenship sentence that also names another status (permanent resident, national, DACA, a visa), wherever the "U.S." periods fall; and an education sentence listing more than one level. Sentences end at line breaks and bullets too, so each bullet of a plain-text list is judged on its own, and a long sentence's excerpt is a window around the matched phrase.

`applies_at` defaults to `program_start`. "at the time of application" / "by the application deadline" → `application`. Explicit calendar dates aren't parsed in v1.

### 6. Lifecycle and staleness

**Refresh** (one function, `refresh_candidates`): extract; for each proposal, an existing candidate with the same key becomes current (a pending one also gets the new excerpt and extractor version); a new key becomes `pending`. Existing candidates not proposed: `pending` ones are deleted, reviewed ones stay with `is_current = false`. Canonical requirements are never deleted or changed by refresh. Refresh runs:

- for a new imported opportunity;
- for an imported opportunity whose canonical fields a sync rewrote, only when the extraction input fingerprint (whitespace-collapsed) changed (not on `last_seen_at`, fetch time, ETag, formatting, or other field changes). Only one record rewrites an opportunity's canonical fields: the earliest-seen active automated record. Before Milestone 6 any source's changed record rewrote them, so two sources describing one posting differently (the discovery feed has no description; a board does) overwrote each other on every change and would make a reviewed posting look changed each time. When the owning record closes, the next earliest active one takes over;
- for a manual create or edit through the API;
- on the owner's explicit "refresh suggestions" request;
- from the catalog scan (§9).

A failing extractor is logged and skipped: the item still syncs, the fingerprint isn't written (the scan retries), and the snapshot outcome doesn't change.

**Source change after review.** When a sync materially changes a non-curated posting (input fingerprint changed) and the owner had reviewed its requirements (`requirements_assessment_status` isn't `unassessed`, or any candidate is accepted/rejected):

1. `requirements_stale_since` is set (kept if already set);
2. a `complete` assessment is downgraded to `partial`, or to `unassessed` when no canonical requirement remains: completeness was asserted for text that no longer exists;
3. candidates refresh (new meanings become pending; reviewed decisions are kept);
4. previously accepted canonical requirements are kept;
5. the opportunity is re-evaluated by the existing automatic evaluation (the fingerprint includes the assessment status).

The UI shows "Posting changed since requirement review. Review requirements again." The owner's next successful review batch clears `requirements_stale_since`. Curated opportunities are never rewritten by sync ([ADR-008 §8](ADR-008-opportunity-ingestion-and-deduplication.md)), so they never go stale this way.

### 7. Review API and completeness

Private, CSRF-protected like every mutation ([ADR-007](ADR-007-single-user-auth-and-private-api.md)):

| Route | |
|---|---|
| `GET /api/opportunities/{id}/requirement-review` | `RequirementReviewResponse`: assessment status, `requirements_stale_since`, `manually_curated`, candidates (pending, accepted, rejected), canonical requirements |
| `POST /api/opportunities/{id}/requirement-review/refresh` | re-extract now (§6); never evaluates (candidates don't affect eligibility) |
| `POST /api/opportunities/{id}/requirement-review` | `RequirementReviewRequest` → `RequirementReviewResult` |

A review batch (`accept` with optional edits, `reject`, optional `assessment_status`) is one transaction. Everything is validated first; any failure (unknown or foreign ID, an ID twice, an invalid edited value, an empty request) changes nothing (`404`/`422`).

- **Accept** (pending or rejected candidate): creates one canonical requirement with the candidate's value or the validated edit (`RequirementBody` rules), `extraction_method = deterministic_parser`, the candidate's `source_text`, `extractor_name`, `extractor_version`; links it. Accepting an already accepted candidate with an edit updates its linked requirement (or recreates it if the owner deleted it).
- **Reject** (pending or accepted): an accepted candidate's linked canonical requirement is deleted. Rejecting never implies completeness, and removing a requirement from a `complete` set without an explicit `assessment_status` downgrades it (to `partial`, or `unassessed` if none remain): completeness was asserted for the larger set, and removing a requirement must never silently make eligibility more permissive.
- **No duplicates**: accepting a suggestion whose (possibly edited) meaning already exists as a canonical requirement links to that row instead of adding another, and a refresh drops pending suggestions the owner has since entered by hand. When `PUT /api/opportunities/{id}` replaces the requirement rows, accepted suggestions are re-linked to the new row with the same meaning, so a later reject or edit still finds it.
- **Concurrency**: both mutating review routes lock the opportunity row for the transaction, so two batches can't both accept the same suggestion.
- **Assessment**: an explicit `assessment_status` is applied as given. `complete` with zero requirements is allowed: the owner asserts there are none. Without it, accepting while `unassessed` moves to `partial`; nothing else changes the status. Extraction alone never changes it.
- **Evaluation**: after the batch, `evaluate_if_changed` runs once for this opportunity. Reject-only on pending candidates changes no input and appends nothing. Fit isn't touched beyond what the shared evaluation recomputes; there's never a catalog pass.

The existing `PUT /api/opportunities/{id}` keeps working: it replaces the requirement set and marks the opportunity curated. Candidates whose canonical requirement it deletes keep `accepted` with `accepted_requirement_id = NULL`.

### 8. Review discovery

The opportunity list returns `pending_requirement_count` and `requirements_stale` per item (one aggregate subquery, no N+1) and accepts server-side filters: `requirements_assessment_status`, `requirement_review` (`pending`: has pending candidates; `stale`: posting changed since review; `needs_review`: either).

### 9. Catalog scan

`python -m app.cli scan-requirements [--batch-size N]`: keyset batches over opportunities, refresh where `requirement_extraction_fingerprint` isn't current, commit per batch, print counts only. Idempotent; never accepts, never changes an assessment status, never evaluates, never marks anything stale. Production runs it only after explicit release approval.

### 10. Scheduled source sync

A GitHub Actions workflow (`.github/workflows/sync-production.yml`) runs `python -m app.cli sync-sources` against Neon twice a day and on manual dispatch. Details, security boundary, and the inactivity limitation are in the [ADR-009 amendment](ADR-009-hosted-deployment-architecture.md#amendment-2026-10-01-scheduled-source-sync-milestone-6). The per-source running-run index stays the only concurrency guard that matters; the workflow's `concurrency` group just avoids queuing overlapping runs.

### 11. Source health

Derived on read from `last_attempted_at`, `last_success_at`, and run history; nothing new is stored. Details in [sources.md](../sources.md#source-health).

### 12. Ashby

Ashby's public Job Postings API for hosted job boards (unauthenticated, `api.ashbyhq.com/posting-api/job-board/{board}`); never the authenticated API. Only the board name is stored; the API URL is built from a hard-coded host. Listed postings only. Details in [sources.md](../sources.md).

### 13. Opportunity type

One canonical matcher: a structured provider field that says intern (Lever `commitment`, Ashby `employmentType`, the feed's program) wins; otherwise the whole-word internship title matcher that already decides `internships_only` scope; otherwise `other`. Broad words (`student`, `junior`, `entry-level`, `new grad`) never count. Type isn't eligibility.

### 14. Deadlines

The `deadline` sort lists upcoming deadlines soonest first, then unknown deadlines, then passed ones (least actionable). The list and filters `deadline_within` (7, 14, 30 days, inclusive of today) and `has_deadline`. "Today" is the client's local date passed as `today` (bounded to years 2000–2999 so date arithmetic can't overflow), falling back to the server's UTC date, so results are deterministic and testable. "Closing soon" means a known deadline 0–7 days away; never for a null deadline. No notifications.

## Consequences

- Imported postings become reviewable in seconds instead of typed from scratch, without weakening the trust boundary: nothing becomes eligible until the owner accepts requirements *and* asserts completeness.
- A posting rewrite after review visibly reopens it instead of silently keeping a stale `complete`.
- Sync runs without the owner, but a disabled schedule or broken source is only visible in Source Health; there are no alerts.
- The extractor misses most requirements written in unusual ways (precision over recall). That's acceptable: a miss leaves the posting where it is today.
- Rejected suggestions can't come back for the same meaning; a genuinely different phrasing that maps to a different meaning can.

## Alternatives Considered

- **Extract straight into canonical requirements.** Rejected: one false positive could make the owner ineligible or hide a requirement, and "found some" would be confused with "found all".
- **Infer `complete` when extraction finds requirements.** Rejected: absence of evidence isn't evidence of absence.
- **AI extraction.** Out of scope ([ADR-003](ADR-003-ai-as-enrichment.md)); the candidate table can hold AI proposals later with a different extractor name.
- **Position- or text-based candidate identity.** Rejected: rephrasing or reordering would resurrect rejected suggestions.
- **Render cron / Vercel cron / a paid scheduler.** Render cron jobs aren't free; Vercel Hobby cron runs at most daily and would have to call the sleeping Render service. GitHub Actions scheduled workflows are free for public repositories.
- **Persisted health labels.** Rejected: they'd go stale exactly when the scheduler stops.
