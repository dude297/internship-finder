# ADR-013: Provider Enrichment and Source Authority

Status: Accepted

Date: 2026-10-03

## Context

Milestone 6 released requirement suggestions, but production produced none: all 1,193 opportunities come from the built-in discovery feed, which has no description field. The feed does name the underlying ATS for many postings (`greenhouse:<board>:<job>`, `lever:<site>:<posting>`, `ashby:<board>:<posting>`, `workday:...`). Greenhouse, Lever, and Ashby boards are already supported adapters with full posting text, but nothing tells the owner which boards would enrich the existing catalog, and when a board and the feed describe the same posting, the *earliest-seen* record owns the canonical fields ([ADR-012 §6](ADR-012-opportunity-requirement-intelligence-and-automation.md#6-lifecycle-and-staleness)). Since the feed is always seen first, a board added later can never replace the feed's description-less text.

Constraints carried forward: the shared pipeline is the only writer of imported data ([ADR-002](ADR-002-shared-ingestion-pipeline.md), [ADR-008](ADR-008-opportunity-ingestion-and-deduplication.md)); exact identifiers only, no fuzzy matching (ADR-008 §6–§7); curated opportunities are never rewritten by sync (ADR-008 §8); suggestions never affect eligibility until accepted (ADR-012); $0/month, no paid APIs, no scraping, no browser automation, no AI ([ADR-004](ADR-004-technology-stack.md), [ADR-005](ADR-005-source-and-profile-ingestion-strategy.md)).

## Decision

### 1. Automated-source authority

Canonical fields have exactly one automated owner per opportunity: the highest-authority active automated source record.

| Rank | Record `source_type` | |
|---|---|---|
| 0 | `ats` (Greenhouse, Lever, Ashby) | the original posting, with its text |
| 1 | `public_feed` (the discovery feed) | discovery metadata about someone else's posting |
| 2 | anything else | |

Ties within a rank: earliest `first_seen_at`, then record ID. So two boards naming one posting never alternate: the first one seen keeps it while active. Authority is derived from the stored `source_type` on every decision; nothing new is stored, and nothing is inferred from company names.

Manual curation stays above all of this: a curated opportunity (`manually_curated_at`) is never rewritten by any sync, owner or not (ADR-008 §8).

### 2. ATS source discovery

Discovery is derived on read from active discovery-feed records already in the database (`external_id` and the stored posting URL). It makes **zero network calls** and stores nothing.

A feed record proves a board only through `provider_identity` in the feed adapter, the same function that derives cross-source identifiers, so discovery and deduplication can never disagree:

- **Greenhouse**: ID exactly `greenhouse:<board>:<digits>` (board matches the shared slug pattern). The ID alone is the identity, because many feed links are company career pages; but a link on a Greenhouse board host (`boards.greenhouse.io`, `job-boards.greenhouse.io`, and their `.eu.` variants) naming a different board is conflicting evidence and yields nothing. Links on the EU Greenhouse hosts aren't suggested: the adapter only calls the US Job Board API.
- **Lever**: ID exactly `lever:<site>:<uuid>` **and** an `https` posting link on `jobs.lever.co` (global) or `jobs.eu.lever.co` (EU) whose first two path segments are the same site and posting ID. The host decides the region; it's never guessed.
- **Ashby**: ID exactly `ashby:<board>:<uuid>` **and** an `https` posting link on `jobs.ashbyhq.com` whose first two path segments are the same board and posting ID. This also adds an `ashby:<board>:<posting>` cross-source identifier to feed postings, so an Ashby board deduplicates onto them.

A link with credentials or an explicit port is not a plain public posting link and proves nothing. Hosts are compared exactly (no suffix matching). The feed's company label is only a *suggested display name*; when feed rows for one board disagree, the most common label wins (ties alphabetically) and the suggestion is flagged ambiguous. Company names are never identity.

### 3. Owner approval

Discovery only suggests. Sources are created only when the owner selects suggestions and submits them (`POST /api/sources/discovery/add`, CSRF-protected): at most 25 per request, validated all-or-nothing. The client sends only `kind`, `identifier`, and `region`; the server re-derives the current suggestion set and refuses anything not in it (no URLs, display names, or other client-supplied fields are accepted). Already-configured suggestions are skipped and reported, never duplicated (the existing unique constraint on `(kind, identifier, region)` is the final guard). New sources default to **Internships only**. Creating sources never syncs them; the owner syncs with the existing controls.

Nothing is created automatically: every board is an explicit owner decision, which bounds the scheduled-sync workload and catalog growth.

### 4. Canonical-field ownership

The owner record rewrites the opportunity's canonical fields (title, organization, description, application URL, location, remote mode, posted date, opportunity type) from its normalized adapter output when:

1. its own item changed (existing behavior);
2. it reactivates (a closed board posting returns);
3. it first attaches to an existing opportunity through deduplication and outranks the current owner (**takeover**: a board added after the feed);
4. the previous owner closes and it is the next owner (**fallback**, §5).

The discovery feed never supplies a description, so a feed owner never writes the `description` field: a feed record taking over keeps the last known posting text instead of erasing it. Every other field is restored from the feed.

Non-owners only update their own source record (provenance, last seen). Unchanged items skip all canonical work, so repeated unchanged runs never flip text.

### 5. Fallback when a direct ATS source closes

When a complete snapshot closes records, the pipeline looks up, for each affected non-curated opportunity, whether a closed record was its owner. If so and another automated record is still active, the new owner's canonical fields are re-derived from its **stored** raw item through its adapter's per-item normalizer (no fetch) and written as in §4. This happens in the same run as the closure, so it doesn't depend on the order sources sync in or on the feed changing (the feed often answers `304`). If no active automated record remains, the opportunity closes and keeps its last canonical text (existing behavior). A stored item that no longer normalizes is logged and skipped; the opportunity keeps its current text.

When the board posting reopens, rule 4.2 makes it the owner again.

### 6. Interaction with requirement staleness and extraction

Every canonical rewrite above goes through the ADR-012 §6 path unchanged: the extraction input fingerprint is compared before and after; only when it changed are reviewed opportunities invalidated (`requirements_stale_since`, `complete` downgraded) and candidates refreshed (`requirements-rules` v1, no new extractor). Then `evaluate_if_changed` runs. Consequences:

- Enriching an unassessed feed posting with board text creates pending suggestions; it never accepts one, never changes the assessment, and never changes eligibility (candidates aren't eligibility inputs). Fit can change, because fit reads title and description.
- Enriching a posting the owner had already reviewed (on the feed's title alone) marks it stale: the text the review was based on changed.
- A fallback and return with identical title and the kept description changes no fingerprint input, so it causes no staleness and no new evaluation.

### 7. Scheduled-sync ordering

`sync_enabled_sources` (the button, the API, the CLI, and the scheduled workflow) syncs direct ATS sources before the discovery feed; within each group, oldest source first, then ID. Correctness doesn't depend on it (§5), but within one run it means a feed sync sees the boards' current state. One source failing never stops the others; the per-source running-run index stays the concurrency guard (ADR-008 §4). No workers or queues.

### 8. Unsupported providers

Workday, Oracle, SmartRecruiters, and every other provider named in feed IDs are **not** fetched, scraped, or reverse-engineered. Discovery only counts them (by a fixed list of known ID prefixes; anything else is `other`), so the owner can see how much of the catalog no supported source can enrich. Their URLs are never requested.

### 9. Production activation

Code release is separate from source activation. After merge and deploy, the owner runs `python -m app.cli source-coverage` and the Sources page's coverage section, picks a bounded first batch of suggestions (largest feed-only coverage first), adds them, syncs them manually, checks deduplication and closures, and measures description coverage and new pending suggestions. The scheduled sync maintains them afterwards. The operational cap and runbook are in [operations.md](../operations.md).

## Consequences

- Existing feed postings with a supported ATS become reviewable without new providers, scraping, or AI.
- Adding a board changes canonical text for opportunities the feed created: titles may change to the board's wording. Reviewed ones visibly go stale (§6) rather than silently keeping a review of different text.
- Feed postings gain an `ashby:` identifier, so the first full feed sync after release reports about 60 postings as `updated` once (identifiers are part of the content hash). Nothing closes, and no fingerprint input changes.
- Description coverage becomes the operational KPI, derived on read.
- A fallback keeps board text after the board closed the posting; the posting's availability already shows which sources still list it.
- More boards mean longer scheduled syncs; the cap in operations.md keeps the twice-daily job inside its 20-minute limit.

## Alternatives Considered

- **Earliest record keeps ownership (status quo).** Rejected: the feed is always first, so boards could never enrich it.
- **Last writer wins.** Rejected: two sources would overwrite each other on every change, flip-flopping text and staleness (the problem ADR-012 §6 fixed).
- **Store discovery candidates or authority in new tables.** Rejected: everything is derivable from existing records; no migration.
- **Automatically add every discovered board.** Rejected: unbounded sync time and catalog growth, and boards the owner doesn't want.
- **Infer boards from company names or fetch posting URLs to detect the ATS.** Rejected: fuzzy identity and arbitrary network access.
- **Workday support.** Rejected for this milestone: no public, documented, unauthenticated posting API; it would mean reverse engineering.
- **Rely on sync order alone for fallback.** Rejected: the feed often answers `304`, so it would never re-run its items.
