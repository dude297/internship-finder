# ADR-008: Opportunity Ingestion and Deduplication

Status: Accepted

Date: 2026-09-27

## Context

Milestone 3 adds automated opportunity discovery. [ADR-002](ADR-002-shared-ingestion-pipeline.md) is the governing principle: every source goes through one shared pipeline, and adapters never write to the database. [ADR-005](ADR-005-source-and-profile-ingestion-strategy.md) orders sources (public feeds, then direct ATS APIs) and requires a license/terms check before consuming another project's data. [ADR-006](ADR-006-core-domain-persistence-model.md) already separates the canonical `opportunities` row from `opportunity_source_records`.

What's new: hundreds to thousands of records per sync, server-side network access, partial failures, the same posting appearing in several sources, postings disappearing upstream, and the owner's manual review work that sync must never erase.

The application is still local and single-user. There's no hosted database, so there's no scheduler.

## Decision

### 1. Source registry

`ingestion_sources` stores **safe configuration only**: a `kind` (`community_feed`, `greenhouse`, `lever`), a validated provider `identifier`, a `region` (`global`/`eu`, Lever only), a display name, `enabled`, run timestamps, and the last `ETag`/`Last-Modified`. It never stores a URL. `(kind, identifier, region)` is unique (PostgreSQL `NULLS NOT DISTINCT`), and a CHECK requires `region` exactly for Lever.

The broad discovery feed is a built-in row seeded by the migration (`community_feed` / `zshah-tech-internships`, "Tech Internship Discovery Feed"). It can be disabled or renamed but not re-pointed: the API can't create `community_feed` sources, and no source's identifier is editable.

### 2. Adapter boundary

An adapter (`app/ingestion/adapters/`) does exactly three things: build its request URL from a **hard-coded provider host + the validated identifier**, validate the top-level response, and turn each item into a typed `NormalizedOpportunity` (or a per-item error). It imports nothing from SQLAlchemy. The shared pipeline (`app/ingestion/pipeline.py`) does everything else.

### 3. Pipeline stages

```text
fetch (safe HTTP client) → validate top level → normalize items
      → identify (source record, then identifiers) → upsert → evaluate (if inputs changed)
      → close unseen records (complete successful snapshots only) → run summary
```

The API, the CLI, and the tests call the same `sync_source` function.

### 4. Run history and partial success

Each sync creates an `ingestion_runs` row (`running` → `success` / `partial` / `failed` / `no_change`) with counts: fetched, normalized, created, updated, deduplicated, unchanged, closed, reactivated, invalid, errors. `ingestion_run_errors` stores bounded, safe per-item problems (stage, short code, message ≤ 500 characters, at most 100 rows per run). No stack traces, headers, credentials, or payload dumps.

Transactions:

1. Commit a `running` run. It is also the per-source "already running" guard: a PostgreSQL partial unique index (`uq_ingestion_runs_one_running_per_source` on `source_id` where `status = 'running'`) allows at most one running run per source, so two concurrent starts can't both proceed; the loser is reported as "already syncing" (`409`), never a `500`. The application's check before the insert only gives the friendly message early. Different sources may sync at the same time. A run left `running` for more than 15 minutes is treated as abandoned and marked `failed`.
2. Fetch and validate outside any database transaction.
3. Process every item in its own savepoint. One malformed or conflicting item rolls back only itself and is recorded; the rest are kept.
4. Finalize the run and commit.

| Outcome | Status | Closes unseen records? |
|---|---|---|
| Network/HTTP failure, oversized or non-JSON response, top-level schema mismatch, incomplete snapshot (declared count ≠ items) | `failed` | No |
| HTTP 304 | `no_change` (no opportunity data rewritten) | No |
| At least one invalid item or item error | `partial` | No |
| Every item processed | `success` | Yes |

### 5. Source record lifecycle

`opportunity_source_records` gains `ingestion_source_id`, `is_active`, `closed_at`, `source_published_at`, `source_updated_at`, and `content_hash`. A record is active while it's present in the source's latest **complete successful** snapshot. When a successful snapshot doesn't contain it, it's marked inactive with `closed_at`; it's never deleted. If it comes back, it's reactivated and `closed_at` is cleared. An opportunity is **open** when at least one automated record is active, **closed** when it has automated records and none is active, and **manual** when it only has manual provenance. Applications, notes, and evaluation history are never touched by closure.

### 6. Cross-source identifiers

`opportunity_identifiers(namespace, value)` is unique and points at one canonical opportunity. Namespaces:

| Namespace | Value | Derived from |
|---|---|---|
| `zshah` | feed item ID | discovery feed `id` |
| `greenhouse` | `<board token>:<job id>` | Greenhouse jobs; feed IDs of the exact form `greenhouse:<token>:<digits>` |
| `lever` | `<region>:<site>:<posting id>` | Lever postings; feed IDs `lever:<site>:<uuid>` **only** when the feed URL is on `jobs.lever.co` (global) or `jobs.eu.lever.co` (EU) with the same site and ID |
| `url` | canonical job URL | any item's application URL (see below) |

Provider identities are derived only from formats that are understood exactly. Nothing is guessed. Board tokens and site slugs are lowercased on both sides. A canonical URL lowercases the scheme and host, drops default ports and the fragment, and keeps the path and query unchanged. A URL without a path or query (a bare careers home page) isn't used as an identity.

### 7. Deduplication order

For every normalized item:

1. Same source + same external ID → update that source record (and its opportunity, unless curated). The same-source/external-ID fast path is still subject to identity-conflict validation. If any current identifier for that item belongs to a different canonical opportunity, the item is rejected as a conflict (rule 3) before the source record is mutated. The one exception is the record's own unchanged URL, which a rule-4 false duplicate legitimately shares with another opportunity.
2. Otherwise look up the item's identifiers. Exactly one existing opportunity → attach a new source record to it (**deduplicated**). None → create a new opportunity.
3. Identifiers pointing at **two or more** different opportunities → **identity conflict**: nothing is merged or changed, the item is recorded as an error, and the run is `partial`.
4. An identifier that matches an opportunity which already has a *different* record from the same source isn't used (one source can't contain the same posting twice). The item gets its own opportunity instead: a false duplicate is preferable to a false merge.

There is no fuzzy matching: same title, same company, or similar text never merges anything.

### 8. Manual-curation protection

`opportunities.manually_curated_at` is set when the owner creates or edits an opportunity through the private API (existing manual rows are backfilled from `updated_at`). Imported opportunities start with it `NULL`. Sync keeps updating source records (raw payload, timestamps, active/closed, hash) for curated opportunities, but never their canonical fields, requirements, or assessment status. There's no "revert to source" action yet.

### 9. Evaluation without history explosion

Evaluations store an `input_fingerprint`: SHA-256 of a canonical JSON serialization (sorted keys, no whitespace, ISO dates) of the rules version, the canonical profile's eligibility inputs (`ProfileInput`), the opportunity's reference dates and assessment status (`OpportunityInput`), and its requirements (type, value, `applies_at`, reference date) sorted by that serialization. Automatic evaluation (ingestion, opportunity create/update) appends a new evaluation only when the fingerprint differs from the latest evaluation's. `POST /api/opportunities/{id}/evaluate` still always appends. Profile changes that affect eligibility re-evaluate everything (the fingerprint changes anyway). The hash is a change detector, not a security control.

Imported opportunities start `unassessed`, so they're at least `needs_verification` (ELIG-REQ-000). Nothing in a feed is turned into a hard requirement.

### 10. External network safety

All ingestion HTTP goes through `app/ingestion/http.py`:

- HTTPS only, to a hard-coded allowlist (`zshah101.github.io`, `boards-api.greenhouse.io`, `api.lever.co`, `api.eu.lever.co`), default port only, no userinfo. User input is only ever parsed into a provider identifier; the server never requests a user-supplied host.
- Resolved addresses must be public (`ipaddress.is_global`); loopback, private, and link-local destinations are refused. (A DNS answer could change between this check and the connection. The allowlisted hosts are large public providers, so this is defense in depth, not the primary control.)
- Connect 5 s / read 20 s timeouts, at most 3 redirects (each target re-checked against the allowlist), a 20 MB body limit (checked on `Content-Length` and while streaming), a JSON content type, and a clear `User-Agent`.
- At most 3 attempts on timeouts, connection errors, 429, and 5xx, with short backoff. `Retry-After` is honored up to 30 s; longer waits fail the run instead.
- `If-None-Match`/`If-Modified-Since` from the stored validators; 304 → `no_change`.
- HTTP library: `httpx2` (BSD-3-Clause, maintained by the Pydantic team), already the test client, promoted to a runtime dependency. No second HTTP stack.

Source HTML (Greenhouse `content`, Lever descriptions) is converted to plain text with the standard library's `html.parser` (scripts and styles dropped). The frontend renders it as text; nothing uses `dangerouslySetInnerHTML`.

### 11. Source licensing and attribution

| Source | Basis | Use |
|---|---|---|
| zshah101 discovery feed | Repository is MIT; we consume its published JSON API only, and copy none of its code | Broad discovery metadata. Its sponsorship, H-1B, skill, and category fields stay in the raw payload and are never hard requirements |
| Greenhouse Job Board API | Public, unauthenticated GET endpoints for published boards | Direct ATS. No application submission |
| Lever Postings API | Public postings endpoints (global and EU) | Direct ATS. No Data API, no candidate submission |
| SuryaHarikrishnan/2027-internship-tracker | Its software license doesn't clearly cover the aggregated listing data | **Not ingested.** Reference only |

This is an engineering source-use review, not legal advice. Details: [docs/sources.md](../sources.md).

### 12. No scheduler

The database is local, so a GitHub-hosted workflow can't update it. Sync is manual: the Sources page, `POST /api/sources/{id}/sync`, `POST /api/sources/sync`, and `python -m app.cli sync-source(s)`. A hosted deployment can add scheduling later by calling the same CLI.

## Consequences

- Adding a source is an adapter plus an enum value, not a new persistence path.
- A malformed item or an identity conflict makes the run `partial`, which also blocks closure for that source until it's fixed. That's deliberate: closing on incomplete information is worse than keeping a stale posting open.
- Direct ATS boards import every published posting, not just internships (their APIs have no reliable internship flag). They're typed `other` unless a structured field says otherwise.
- Deleting an imported opportunity deletes its source records, so the next sync re-imports it. Hiding is future work.
- Profile re-evaluation stays synchronous and touches every opportunity. At a few thousand rows it's acceptable locally but should move to batched/background work before hosted use.

## Alternatives Considered

- **Fuzzy title/company matching.** Finds more duplicates but produces false merges, which are much worse (two postings' requirements and tracking tangled together). Rejected for this milestone.
- **Closing records on any run where they weren't seen.** Simple, but a timeout or a truncated response would close everything. Rejected: only complete successful snapshots close.
- **One transaction per sync.** One bad item would discard a thousand good ones. Rejected in favor of per-item savepoints.
- **Adapters writing their own rows.** Violates ADR-002. Rejected.
- **Storing each source's URL.** Would turn the registry into a server-side request proxy. Rejected: URLs are built from hard-coded hosts.
- **`requests` or `urllib`.** `httpx2` is already installed for tests, has timeouts, streaming, and mock transports. A second stack isn't needed.
- **Scheduled GitHub Actions sync.** Can't reach a local database. Deferred to a hosted architecture.
