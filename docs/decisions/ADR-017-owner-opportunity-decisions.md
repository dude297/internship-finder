# ADR-017: Owner Decisions on Opportunities (Hide and Revert to Source)

Status: Accepted (Milestone 9, on the feature branch; subject to owner review)

Date: 2026-10-06

## Context

Two owner decisions had no durable form:

- **"Not interested."** Deleting an imported opportunity deletes its source records and identifiers ([ADR-008 §5](ADR-008-opportunity-ingestion-and-deduplication.md)), so the next sync that still lists the posting imports it again as a new opportunity. The owner could not keep a posting out of the list.
- **Undoing an edit.** Any owner edit marks an opportunity curated and sync then never rewrites its fields or requirements ([ADR-008 §8](ADR-008-opportunity-ingestion-and-deduplication.md)). There was no way back to the source's content.

Constraints carried forward: provenance and source records are never deleted by an owner decision ([ADR-006](ADR-006-core-domain-persistence-model.md)); the highest-authority active automated record owns canonical content ([ADR-013 §1](ADR-013-provider-enrichment-and-source-authority.md)); owner-curated content is never silently overwritten; eligibility and fit are re-evaluated only through the fingerprinted path ([ADR-008 §9](ADR-008-opportunity-ingestion-and-deduplication.md#9-evaluation-without-history-explosion)).

## Decision

### 1. Hide is two nullable columns on `opportunities`

`dismissed_at` (timestamptz) and `dismissed_reason` (varchar(30), optional, one of `not_interested`, `not_eligible`, `already_applied`, `other`, validated by the API). CHECK: a reason requires `dismissed_at`. One additive migration (`d4f8a1c6e2b9`); no data change; downgrade drops the columns.

The sync pipeline never reads or writes them. A hidden opportunity keeps receiving source updates, closure, reactivation, fallback and evaluation exactly like a visible one, and because its source records and identifiers still exist a later sync deduplicates onto it instead of creating a new opportunity. Hiding does **not** set `manually_curated_at`: it is a visibility decision, not content.

### 2. Visibility is a list filter, hidden excluded by default

`GET /api/opportunities?hidden=exclude|include|only`, default `exclude`. Every sort, including `recommended`, therefore excludes hidden opportunities by default. Direct links to a hidden opportunity keep working; its detail page says it is hidden. Eligibility, fit, application tracking, and source coverage counts are unchanged by hiding.

### 3. API

All owner-only and CSRF-protected by the existing router dependency ([ADR-007](ADR-007-single-user-auth-and-private-api.md)):

- `PUT /api/opportunities/{id}/dismissal` with optional `{"reason": ...}`: hide. Idempotent; a repeat keeps the first `dismissed_at`, and keeps the existing reason unless a new one is given.
- `DELETE /api/opportunities/{id}/dismissal`: un-hide.
- `POST /api/opportunities/{id}/revert-to-source`: see §4.

`DELETE /api/opportunities/{id}` is unchanged (still the only way to remove a manual opportunity). For imported opportunities the UI offers **Hide** next to Delete and the delete confirmation says a sync will import it again.

### 4. Revert to source is explicit and reuses the sync authority rules

For an imported, curated opportunity, `revert-to-source`:

1. Picks the owner record by the same ranking as sync ([ADR-013 §1](ADR-013-provider-enrichment-and-source-authority.md)): the highest-authority **active automated** record (ATS, then feed, earliest first seen, then ID).
2. Re-derives its item from the stored raw payload through that source's own adapter (the [ADR-013 §5](ADR-013-provider-enrichment-and-source-authority.md) fallback path; no network fetch).
3. Rewrites the source-derived canonical fields with `_write_canonical`, clears the dates and date-trust fields the source doesn't write (only the program registry writes them), deletes the recorded requirements and candidates, resets the assessment to `unassessed`, clears staleness and the extraction fingerprint and `manually_curated_at`, then refreshes candidates from the restored text.
4. Re-evaluates through `evaluate_if_changed` (fingerprinted), so no history row is added if nothing eligibility- or fit-relevant changed.

Details: a public-feed owner never erases the last known description (the feed has none; same guard as sync, ADR-013 §4). A registry owner restores its dates and date-trust fields from its stored item. The opportunity row is locked first, as in the sync owner query. Candidates are deleted and re-proposed, so suggestions the owner previously rejected or accepted reappear as **pending** after a revert.

It is refused (`409`, message shown to the owner, nothing changed) when the opportunity is manual-only, has no owner edits, has no active automated record, or the stored item no longer normalizes. The UI requires confirmation and states that edits and recorded requirements are discarded; application tracking and hidden state are kept. After a revert the opportunity is not curated, so later syncs own its content again.

## Consequences

- Positive: "not interested" survives every sync with no new tables; no sync code changed; revert reuses existing authority and fingerprint code.
- Negative: revert discards accepted requirements along with the edits (the owner re-reviews, as for a new import). Hidden opportunities still count in per-source coverage and are still evaluated (cheap; keeps un-hide instant).
- Rollback: the columns are additive, so rolling the app back to Milestone 8.1 without downgrading ignores them and **un-hides** every hidden opportunity (it would also let it reappear in lists); downgrading the migration deletes the hidden state.
- Not built: bulk hide, a hidden count badge, per-row list actions, hiding by company or source. Hiding is per opportunity; a posting that a source re-lists under a different identity can appear as a new opportunity ([ADR-008 §6](ADR-008-opportunity-ingestion-and-deduplication.md)).
