# ADR-014: Structured Source Expansion and the Curated Program Registry

Status: Accepted

Date: 2026-10-04

## Context

Milestone 7 ([ADR-013](ADR-013-provider-enrichment-and-source-authority.md)) made direct ATS boards outrank the discovery feed and added feed-derived source discovery. In production that left 20 direct boards (13 Greenhouse, 2 Lever, 5 Ashby) and description coverage of 294 / 1,313 open opportunities (22.4%). The feed still names about 40 SmartRecruiters postings (`smartrecruiters:<Company>:<id>` with a `jobs.smartrecruiters.com/<Company>/<id>` link) that no adapter can enrich.

The programs that matter most to a high-school senior / incoming freshman (NASA and national-lab programs, university summer research, STEM service programs) have no structured API, and several forbid crawling ([research](../research/spring-summer-2027-source-expansion.md)). Their dates are seasonal and often published late, so a "typical" February deadline must never be presented as this cycle's deadline.

Constraints carried forward: the shared pipeline is the only writer of imported data (ADR-002, ADR-008); exact identifiers only (ADR-008 §6); curated opportunities are never rewritten by sync (ADR-008 §8); suggestions never affect eligibility until accepted (ADR-012); ATS > feed authority (ADR-013); $0/month, no scraping, no browser automation (ADR-004, ADR-005).

## Decision

### 1. SmartRecruiters: public Posting API only

SmartRecruiters' authentication guide states that some APIs "provide access to public data and don't require authentication by design" and names the **Posting API** ([developers.smartrecruiters.com/docs/authentication](https://developers.smartrecruiters.com/docs/authentication), checked 2026-10-04). The INTERNAL destination requires an OAuth scope; PUBLIC postings don't. So SmartRecruiters is a Tier 1 source: documented public-data access, no customer API key.

- Host: `api.smartrecruiters.com` only, added to the ingestion allowlist ([ADR-008 §10](ADR-008-opportunity-ingestion-and-deduplication.md)). Every other rule of `app/ingestion/http.py` applies (HTTPS, port 443, no userinfo, public DNS, bounded size/redirects/retries).
- Endpoints: `GET /v1/companies/{company}/postings?limit=100&offset=N&destination=PUBLIC` (list) and `GET /v1/companies/{company}/postings/{id}` (detail). Nothing else: no candidate, application, job-administration, feed/publications, or INTERNAL/INTERNAL_OR_PUBLIC calls, and never an API key or token.
- Owner configuration: a company identifier, or a `https://jobs.smartrecruiters.com/<company>` link from which only the identifier is kept (the link is never requested). Refused: other schemes or hosts, lookalikes and trailing-dot hosts, credentials, explicit ports, identifiers outside `^[a-z0-9][a-z0-9_-]{0,63}$` after lowercasing. Identifiers are case-insensitive at the provider (verified on the live endpoint) and stored lowercased. Arbitrary API URLs are never accepted.
- Source kind `smartrecruiters`, record `source_type` `ats`. Default scope `internships_only`, like every board.

### 2. Multi-request adapters, pagination, and the detail budget

An adapter may provide `collect(request)` instead of a single `url` fetch. The pipeline passes the source's config, scope, and its stored raw items by external ID; `collect` returns the payload `parse` reads, or raises `FetchError`/`SnapshotError`, which fail the run without changes. There are no conditional requests for such sources.

SmartRecruiters `collect`:

1. **List.** Walks `offset` in pages of 100 (the documented maximum) until `totalFound` is reached. The walk must be complete and consistent: an empty page before `totalFound`, a `totalFound` that changes mid-walk, a page that isn't the expected shape, or more than 50 pages (5,000 postings) fails the snapshot. A failed walk never closes anything.
2. **Admission.** Under `internships_only`, the same title matcher as the pipeline (`is_internship_title`) selects which postings get a detail request; the pipeline filters again after normalization, so filtering is identical either way.
3. **Detail.** For each admitted posting, the stored detail is reused when the stored list item equals the new one exactly; otherwise one detail GET, at most **100 per run**. A detail must name the same posting ID and company as the list item. Because the list has no "updated" field, each reused detail is also refetched once every 7 days (a fixed rotation by posting ID), only from budget left after new and changed postings; a failed refresh keeps the stored detail and doesn't make the run partial.
4. **Partial semantics.** A detail that fails, mismatches, or exceeds the budget turns that posting into an item error: the run is `partial`, so nothing closes, the posting's existing record and canonical text are untouched, and the next run retries it. A posting never becomes canonical with a missing or wrong description because of a detail failure.

Request bound per SmartRecruiters source and run: ≤ 50 list + ≤ 100 detail requests (each with the client's existing ≤ 3 attempts). A first sync of a large internship board may need several partial runs to fetch every detail; that is deliberate (no closures until complete).

Closure: only a complete list walk with every admitted posting resolved closes records missing from it, exactly as for other sources. A company identifier with no public postings answers 200 with zero items, so a renamed company closes its postings on the next complete run (they're closed, never deleted, and reopen if they return).

### 3. SmartRecruiters identity and discovery

- Identifier `smartrecruiters:<company>:<posting-id>` (company lowercased, ID digits), plus the posting page URL identifier only when that URL is the company's own posting page (`https://jobs.smartrecruiters.com/<company>/<id>[-slug]`): the tenant controls `postingUrl`, so a link elsewhere never becomes a dedupe identity.
- The feed proves a SmartRecruiters identity only when **both** its ID is `smartrecruiters:<company>:<digits>` and its link is a plain `https://jobs.smartrecruiters.com/<company>/<id>` (optionally `-<title-slug>`) naming the same company and posting, exactly like Ashby (ADR-013 §2). No identity is ever inferred from an organization name.
- Discovery (`GET /api/sources/discovery`, `source-coverage`, Source Coverage, bulk add) gains SmartRecruiters through that one function, with every ADR-013 §2–§3 rule unchanged: derived on read, zero network, bulk add creates configuration only, owner selects, default `internships_only`.

### 4. Authority

SmartRecruiters records are `ats`, so ADR-013's ATS > feed authority, takeover, and fallback apply unchanged. No new rank.

### 5. The curated program registry is a built-in source

The registry is a repository data file, `backend/data/program_registry.json`, imported by a built-in source of kind `curated_registry` through the shared pipeline. Its records have their own `source_type`, `curated_registry` (authority rank 2: it never merges with anything, see below).

- **Identity:** `curated:<slug>:<cycle>` only. Registry items deliberately emit **no URL identifier**, so a program page that happens to equal a feed link can never merge a curated program into an unrelated posting.
- **Idempotency:** the pipeline's content hash makes an unchanged entry a no-op; an edited entry updates the same opportunity; a new cycle (`2028`) is a new opportunity; an entry removed from the file is closed (not deleted) after a complete import.
- **Why not manual provenance:** a `manual` record sets `manually_curated_at`, which blocks every later sync, so the registry could never correct its own entry. As an automated source it updates the opportunities it owns and nothing else.
- **Owner edits win:** if the owner edits a registry opportunity through the app, the API sets `manually_curated_at`, and from then on the registry never rewrites it (ADR-008 §8). Requirements and the assessment status are never written by any source.
- **No network:** `collect` reads the bundled file. The source can be disabled but never created, re-pointed, or filtered (`builtin`, scope `all`). It is seeded by the migration and participates in scheduled sync with the ATS tier.

### 6. Date trust: verified vs typical

| Registry field | Stored as | Meaning |
|---|---|---|
| `verified.deadline`, `verified.start_date`, `verified.end_date` | canonical `application_deadline`, `start_date`, `end_date` | Published by the program for this cycle as firm dates and checked on `last_verified`. A date the program itself calls tentative, pending approval, or subject to change is **not** verified: it goes in the description or a typical window |
| `typical_open_window`, `typical_close_window` | text columns of the same names | What past cycles did ("February"); display text, **never a date** |
| `verify_by` | `verify_by` date | From this date on, the UI shows **Needs date verification** |
| `cycle` | `program_cycle` | The cycle the entry describes |

- A typical window never populates `application_deadline`, so deadline sorting, deadline filters, and eligibility (which evaluates requirements on the deadline/start date) only ever see verified dates.
- `verify_by` passing never closes or hides anything: it is a display state and a filter.
- Only the registry writes these columns (`_write_canonical` writes dates for `curated_registry` records only); every other source still never touches dates. Writing a verified date can change an eligibility evaluation, exactly as an owner-entered date would; suggestions still can't.
- The new `NormalizedOpportunity` fields are omitted from the content hash while unset, so every pre-M8 source keeps its exact hashes (no mass "updated" run after the upgrade).

### 7. Registry content and update mechanism

- Public facts and owner-written paraphrases with official source links only: no copied page prose, no personal data, nothing behind a login. Every entry carries `source_url` and `last_verified`.
- Strict schema (unknown keys rejected, https links without credentials, bounded text, `end_date ≥ start_date`); a malformed file fails the import (no partial registry); a malformed entry is an item error (partial run, nothing closes).
- Updating = a reviewed pull request to the file, then a sync (manual or scheduled). There is no in-app editor; this is not a CMS.
- Initial content: a small set (10–20) of programs whose facts could be sourced on 2026-10-04. A 2027 date that isn't published yet stays `null`.

### 8. Requirement extraction

Every source's description, including SmartRecruiters detail text and the registry's description plus eligibility summary, goes through the existing ADR-012 extractor exactly once per text change. Candidates stay **pending**; nothing is auto-accepted, no canonical requirement is created, and the assessment status and eligibility don't change because of a suggestion. The extractor itself is unchanged in M8; a recall analysis is recorded in [requirement-extractor-recall.md](../research/requirement-extractor-recall.md).

### 9. Scheduled sync

Order stays ADR-013 §7: direct ATS sources (now including SmartRecruiters) and the registry first, the discovery feed last. With the ADR-013 operational cap of 50 enabled ATS sources unchanged, SmartRecruiters adds at most 150 requests per source per run.

### 10. Exclusions

Not implemented and not allowed by this ADR: Workday, Oracle Cloud HCM internal endpoints, iCIMS internal endpoints, Eightfold, Phenom, SuccessFactors, Taleo, NSF ETAP crawling, NASA STEM Gateway crawling, browser automation, CAPTCHA handling, third-party scraping services, SmartRecruiters authenticated/candidate/application APIs. USAJOBS needs an owner-held key and a User-Agent carrying the owner's email; it is deferred to a separate milestone with its own decision (see the research document's future card).

## Consequences

- One migration (`a8c3e5f7b9d1`): enum widening, four nullable opportunity columns, the seeded registry source; no backfill. Downgrade refuses while SmartRecruiters sources or registry records exist.
- The built-in source list now has two entries (feed and registry).
- A large SmartRecruiters internship board may take several runs to fill every description; runs in between are `partial` (Source Health shows a warning) and close nothing. Likewise, a posting whose detail fails on every run keeps that source partial, so its removed postings stay open until it resolves (the existing "recurring partial run blocks closure" limitation, now reachable through detail failures; false-open, never false-closed).
- Registry dates are only as current as the file. `verify_by` makes the staleness visible instead of hiding it.

## Alternatives Considered

- **Registry via manual opportunities (CLI import):** rejected; `manually_curated_at` would block the registry from ever updating its own entries, and identity/idempotency would need a second implementation.
- **Typical dates in `application_deadline` with a flag:** rejected; every deadline consumer (sort, filters, eligibility) would have to remember the flag.
- **Fetch every SmartRecruiters detail on every run:** rejected; unbounded N+1. Reusing stored detail for unchanged list items keeps steady-state runs to the list pages.
- **Treat SmartRecruiters detail failures as "no description":** rejected; an ATS owner would erase the feed's or its own earlier text and look like a material change.
- **Oracle Cloud HCM adapter:** rejected for M8; no documented anonymous public API was established (see research).
