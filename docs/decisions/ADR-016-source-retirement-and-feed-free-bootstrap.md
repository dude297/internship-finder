# ADR-016: Source Retirement and Feed-Free Bootstrap

Status: Accepted (Milestone 8.2, on the feature branch; subject to owner review)

Date: 2026-10-06

## Context

[ADR-015 §9](ADR-015-freshness-requirements-v2-and-independent-discovery.md#9-the-community-feed-is-optional) made the community feed optional for *discovery*, and [§11](ADR-015-freshness-requirements-v2-and-independent-discovery.md#11-known-gaps-toward-full-self-sufficiency-not-in-this-milestone) listed what was still missing: disabling a source leaves its records active, so a retired feed's ~1,000 feed-only postings stay open as `source_warning` forever; and a new installation starts from the migration-seeded feed row (enabled), with first-run docs that assume it.

Constraints carried forward: the shared pipeline is the only writer of imported data (ADR-002, ADR-008); records are closed, never deleted (ADR-008 §5); a closing canonical owner falls back to the next source (ADR-013 §5); curated opportunities are never rewritten by sync (ADR-008 §8); owner-approved activation with at most 50 enabled direct sources ([operations.md](../operations.md#operational-source-cap)); `$0/month` (ADR-004).

## Decision

### 1. One closure path

The closure and ADR-013 §5 fallback that ran inline when a complete snapshot no longer listed a posting is extracted, unchanged, into `pipeline.close_records(db, record_ids, opportunity_ids, now, context)`. The snapshot closure and retirement both call it; retirement reimplements nothing.

### 2. `retire-source`

`python -m app.cli retire-source SOURCE [--apply]` (SOURCE is an ID or key). Dry run by default. With `--apply`, in one transaction and under a row lock on the source:

1. refuse if the source has a `running` run younger than the abandonment window (exit 1);
2. close all the source's active records via `close_records`, so canonical content falls back to the next remaining automated source and opportunities with another active record stay open;
3. clear the source's HTTP validators, then set `enabled = false`;
4. commit. Any failure rolls the whole transaction back: the source stays enabled and nothing is closed.

It prints counts only: records closed, opportunities closed (no active record left), opportunities that stayed open via another source, fallbacks applied, owner-curated preserved, and whether the source is (would be) disabled. It never deletes a row, never rewrites a curated opportunity (the existing fallback already excludes them), and never touches manual opportunities (they have no source records) or application tracking. A second run closes nothing. It works for any source, built-in ones included (they can be disabled; there is no delete path). No API endpoint: the owner-run CLI is the supported path.

**Rollback:** re-enable the source and sync it. The validators were cleared, so the sync is a full snapshot (not a `304`) and the normal reactivation path reopens its records. Content the fallback moved is re-derived by the usual ADR-013 rules.

### 3. `bootstrap-sources`

`python -m app.cli bootstrap-sources [--tags TAG ...] [--disable-feed] [--dry-run] [--sync]`:

- adds Direct Source Catalog entries (optionally filtered by tag) through `direct_catalog.add_from_catalog`, the same validation and creation path as `POST /api/sources/catalog/add`, in 25-entry batches inside one transaction, scope `internships_only`;
- refuses (exit 1, nothing written) an unknown tag, or when enabled direct sources would exceed 50;
- ensures the curated registry source exists (the migration seeds it; this only repairs a database without it);
- `--disable-feed` disables the feed only when it has no open postings; otherwise it refuses and points to `retire-source`;
- never syncs unless `--sync` is given.

No migration: the feed row stays seeded (existing deployments and tests rely on it); a feed-free installation is the bootstrap's result, not a different schema.

## Consequences

- The owner can retire the feed (or any board) without orphaned "open" postings, with a dry run first and a one-step rollback.
- A fresh install is usable without the feed: bootstrap, sync, and every direct-backed opportunity is discovered, ranked, evaluated and trackable (`test_feed_off_resilience.py`).
- Still not solved: new-company *discovery* without the feed remains the hand-verified catalog or manual Add Source; the feed-only postings at unsupported employers close on retirement, by design.
- ADR-015 §11 is superseded in part by this ADR (the retire command and the feed-free bootstrap).
