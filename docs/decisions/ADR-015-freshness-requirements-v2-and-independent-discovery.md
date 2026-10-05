# ADR-015: Listing Freshness, Requirement Extraction v2, and Independent Discovery

Status: Accepted (Milestone 8.1, on the feature branch; subject to owner review)

Date: 2026-10-05

## Context

After Milestone 8 ([ADR-014](ADR-014-structured-source-expansion-and-program-registry.md)) production holds 1,626 open opportunities: 616 backed by a direct ATS board, 997 known only through the community discovery feed, 13 curated registry programs. "Open" means at least one active source still lists the posting (ADR-008 §5). That is correct but says nothing about how strong the evidence is: a posting confirmed on the company's own board an hour ago and one whose only source has been partial for days look the same.

`requirements-rules` v1 (ADR-012 §5) produced 18 pending suggestions from 629 descriptions and mislabels "U.S. citizens or permanent residents" as work authorization ([recall analysis](../research/requirement-extractor-recall.md)).

Finally, most direct boards were found *through* the community feed (ADR-013 §2), so the feed is still part of discovery. A production audit shows the feed carries almost none of the large employers the owner cares about (0 open postings for Google, Apple, Meta, Microsoft, OpenAI, Anthropic; [audit](../research/catalog-freshness-audit.md), [matrix](../research/direct-company-source-matrix.md)).

Constraints carried forward: derived state over stored truth (ADR-012 §11 source health); suggestions never affect eligibility until accepted (ADR-012); ATS > feed authority (ADR-013 §1); allowlisted, keyless, documented sources only, no scraping (ADR-004, ADR-005, ADR-008 §10).

## Decision

### 1. Listing freshness is derived on read, never stored

`app/services/freshness.py` derives one state per opportunity from its active automated source records and each source's current health ([ADR-012 §11](ADR-012-opportunity-requirement-intelligence-and-automation.md)). No column, no `verified_open` flag.

| State | Evidence | UI wording |
|---|---|---|
| `direct_verified` | an active record from a direct source (company ATS, or an approved first-party career source: `source_type` `ats` or `career_page`) whose source is **healthy** (latest finished run success/no-change, last success within 24 h) | "ATS verified · 3h ago" / "Verified on the company's own job board (ATS) in its latest complete sync" |
| `program_listed` | curated registry record, registry healthy, `verify_by` not reached | "Program checked Oct 4 · re-check Oct 9" (the registry's `last_verified` and `verify_by`) |
| `program_recheck` | curated registry record whose `verify_by` was reached | "Program info needs re-check" |
| `feed_current` | the community feed lists it and the feed is healthy, and no healthy direct source does | "Feed current · 4h ago" |
| `source_warning` | open, but none of its listing sources is healthy (partial, failed, stale, disabled) | "Verification incomplete" — closure information may be incomplete |
| `manual` | owner-managed, no automated source | "Added manually" |
| `closed` | no active automated record | (existing closed label) |

Precedence is the order above (direct beats registry beats feed). A partial direct source with a healthy feed is `feed_current` (the feed still lists it). `freshness_checked_at` is the best evidence's source `last_success_at`. Wording never says "definitely" or "guaranteed" open.

The list endpoint computes every source's health once (two set-based queries) and reads the registry's `last_verified` for the page's programs in one more; the statement count is independent of page size (tested). Filters: `freshness=direct_verified|needs_review` (needs review = `source_warning` ∪ `program_recheck`), both in SQL using the healthy-source ID set. The detail response adds each source record's `source_health` and `source_last_success_at`.

### 2. "New" means first found by Internship Finder

`first_seen_at` (never the provider's `posted_at`) drives a client-side **New** badge (< 7 days), a `discovered_within=1|7` filter, and `sort=discovered`. Tooltips show first-found and company-posted dates separately. Known limitation: activating a new board marks all its postings New for a week (they *are* new to the app); the posted date beside it tells the owner how old the posting is.

### 3. Live application-URL checks: rejected

Periodic HEAD/GET of application URLs is not implemented. Provider snapshots already prove removal for direct boards; HTTP pings produce false signals (200 for closed JS-rendered postings, redirects to generic pages, 403/429 from bot protection on CI addresses) and ~2,000 wasted requests a day ([tracker audit](../research/tracker-gap-audit.md)). A user-triggered, advisory "check link" for a few saved items could be reconsidered later; it must never change stored state.

### 4. Requirement extraction `requirements-rules` v2

The extractor version becomes `2`; v1 candidates keep `extractor_version = "1"`, so stored history stays interpretable. Same pure, deterministic architecture, no AI. Rule families, exact labels, guards, and the 200+ sentence corpus: [requirement-extractor-v2.md](../research/requirement-extractor-v2.md).

- Value shapes don't change. Citizenship alone → `citizenship` `US`. "Citizen **or** permanent resident" → `other` "U.S. citizen or permanent resident" (never citizenship, never work authorization). "U.S. person"/ITAR/EAR → `other` "U.S. person (export control)". Work authorization and "without sponsorship" are distinct `work_authorization` labels. Clearance keeps its v1 label.
- Graduation windows, class standing, and "return to school" have no evaluable type, so they become `other` with deterministic normalized labels (verification-oriented, never evaluated).
- Every free-text label is fixed or normalized, so the semantic key (ADR-012 §3) is stable across wordings. v1 labels that survive are unchanged, so v1 reviewed decisions keep their keys.
- Rescan: the v1→v2 fingerprint change makes the catalog scan re-extract every opportunity. The existing lifecycle (ADR-012 §6) guarantees reviewed decisions survive: rejected candidates are never resurrected (same key → same rejected row), accepted ones and their canonical requirements are untouched, only *pending* v1 candidates no longer proposed are deleted. Candidates stay `pending`; nothing changes canonical requirements, assessment status, or eligibility. Tested in `test_m81_extractor_rescan.py`.

### 5. Independent Discovery Coverage

Over open opportunities, **independent** = has an active record from a non-feed automated source (direct ATS, approved first-party, curated registry) or is owner-managed. Feed-only postings never count, however they were found. Reported on Source Coverage with the breakdown (direct ATS, first-party, registry, manual-only, feed-only, direct-fresh). Production at release time: 629 / 1,626 = 38.7%.

### 6. Direct Source Catalog

`backend/data/direct_source_catalog.json` holds owner-reviewable source **configuration** only: organization, provider kind, identifier, region, official careers URL, the verification evidence, verification date, tags. No listing data, no tracker data. An entry exists only after official verification (company careers page and/or the provider's documented API answering for that identifier with that company's postings); a company name is never turned into a guessed slug.

- Loaded and validated at startup: every identifier must be the canonical output of the same parser Add Source uses (`services/sources.parse_reference`), no duplicates, HTTPS careers URL, fixed tag set.
- `GET /api/sources/catalog` lists entries with `already_configured`; `POST /api/sources/catalog/add` (owner, CSRF) adds 1–25 entries all-or-nothing with scope `internships_only`, exactly like discovery add (ADR-013 §3). It never syncs and nothing is enabled automatically.
- The Sources page shows **Verified Direct Sources** with tag filters and bulk add.
- 36 entries at 2026-10-05 (each verified by a documented-API GET that day).

### 7. Workable and Pinpoint adapters

Both pass the implementation gate: provider-documented, keyless, free, fixed provider hosts, stable IDs, one complete snapshot per request.

- **Workable**: `GET https://www.workable.com/api/accounts/{account}?details=true` (documented jobs widget API), redirected to `apply.workable.com`; both hosts allowlisted. External ID = shortcode; posted date = `published_on`; no deadline. Unknown account → 404 → failed run, nothing closes.
- **Pinpoint**: `GET https://{company}.pinpointhq.com/postings.json` (documented). The allowlist gains one pattern, a single DNS label under `pinpointhq.com` (`ALLOWED_HOST_PATTERN`); the adapter validates the label and accepts posting URLs only on the same company subdomain. No posted date is invented; `deadline_at` only when stated. Unknown company → 404.
- Both: a 200 with an empty list is a complete snapshot (same accepted limitation as other single-request providers), schema mismatch fails the snapshot, item errors make the run partial. One request per source per run.
- Migration `b7e3d9f1a2c4` adds the two kinds to the `ingestion_sources.kind` CHECK (downgrade refuses while such sources exist).

### 8. No first-party company adapter yet; no new provenance enum

No company-specific source passed the gate in this milestone: Apple, Amazon, Microsoft, Netflix, NVIDIA (Eightfold) expose undocumented endpoints or sitemaps whose third-party use isn't documented (YELLOW); Google's and Meta's robots rules forbid it (REJECT). The existing `career_page` `source_type` is the provenance a future approved first-party source will use; freshness and coverage already treat it as direct. Authority (ADR-013 §1) is unchanged in this milestone; if a first-party source is added, it must rank with `ats` in `_SOURCE_RANK` in that change. No `FIRST_PARTY` enum is added.

### 9. The community feed is optional

With the feed disabled or failing, direct boards, the registry, and manual entry still discover, deduplicate, rank, evaluate eligibility and fit, and track applications; the scheduled sync never needs it (`test_feed_off_resilience.py`). What still depends on the feed: board *suggestions* (ADR-013 §2 discovery) and the ~780 feed-only postings whose employers use unsupported platforms (Workday, Oracle, custom sites).

## Consequences

- The owner sees how much to trust "open" at a glance and can filter to direct-verified or needs-review postings.
- v2 proposes more suggestions; the owner reviews them. False hard requirements are the main risk and are attacked by a separate adversarial suite.
- Activating catalog boards is the main lever for coverage and self-sufficiency; it remains an explicit owner action, bounded by the operational source cap ([operations.md](../operations.md#operational-source-cap)).
- Two new hosts and one host pattern widen the network boundary slightly; both are fixed provider domains with validated identifiers.
