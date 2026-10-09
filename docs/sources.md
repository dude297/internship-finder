# Opportunity Sources

Every source feeds the shared ingestion pipeline ([ADR-002](decisions/ADR-002-shared-ingestion-pipeline.md), implemented by [ADR-008](decisions/ADR-008-opportunity-ingestion-and-deduplication.md)). No source writes to the database directly. The source strategy is layered, not crawler-only ([ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md)).

The source review below is an engineering source-use review, not legal advice.

## Source Layers

| Priority | Layer | Approach |
|---|---|---|
| 1 | Existing public structured feeds | Consume where legally and technically appropriate (license/terms checked) |
| 2 | Direct ATS sources | Greenhouse, Lever, Ashby, other structured ATS APIs |
| 3 | High-school / early-college specific | University summer research and labs, research internships, fellowships, government and nonprofit STEM programs, startup internships, hackathons, technical summer programs, accelerators, scholarships with technical/project components, incoming-freshman and first-year undergraduate programs |
| 4 | Custom career pages | HTML parsing where needed |
| 5 | Browser automation | Only when simpler structured approaches are unavailable |

Priority 3 is strategically the most important layer for this user, even though it's harder to automate.

## Source Review and Attribution

Last reviewed: 2026-10-05 (through Milestone 8.1; earlier rows 2026-09-27).

| Source | Role | API / docs | License / usage basis | Attribution | Implemented? | Notes |
|---|---|---|---|---|---|---|
| zshah101 Summer/Fall Tech Internships feed | Broad discovery (layer 1), built in | Public JSON feed: `https://zshah101.github.io/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships/api/jobs.json` ([repository](https://github.com/zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships)) | Repository is MIT-licensed. We consume only the published API; none of its code is copied | Listed here and shown as "Tech Internship Discovery Feed" on every imported record; each record keeps the original posting link | **Yes** (Milestone 3) | Factual listing metadata; external source links retained. Source-provided sponsorship, H-1B, skill, and category classifications are **not** hard eligibility; they stay in the raw payload only |
| Greenhouse Job Board API | Direct ATS (layer 2), per-company boards | `GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs` then `?content=true` (or `/jobs/{id}` on a large board, [ADR-022](decisions/ADR-022-large-board-greenhouse.md)) ([docs](https://developers.greenhouse.io/job-board.html)) | Public GET endpoints, no authentication, intended for publishing a company's board | The configured organization name; original posting link kept | **Yes** (Milestone 3) | Published board data only. The application-submission endpoint is never used |
| Ashby Job Postings API | Direct ATS (layer 2), per-company hosted job boards | `GET https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=false` ([docs](https://developers.ashbyhq.com/docs/public-job-posting-api)) | Public GET endpoint, no authentication, intended for publishing a company's hosted job board | The configured organization name; original posting link (`jobUrl`) kept | **Yes** (Milestone 6) | Listed postings (`isListed: true`) only. The authenticated Ashby API and application submission are never used |
| SmartRecruiters Posting API | Direct ATS (layer 2), per-company | `GET https://api.smartrecruiters.com/v1/companies/{company}/postings` and `.../postings/{id}` ([docs](https://developers.smartrecruiters.com/docs/authentication)) | Documented public data, no authentication | The configured organization name; original posting link kept | **Yes** (Milestone 8) | PUBLIC destination only; see the section below |
| Workable widget API | Direct ATS (layer 2), per-account | `GET https://www.workable.com/api/accounts/{account}?details=true` | Documented public jobs widget, no key | The configured organization name; original posting link kept | **Yes** (Milestone 8.1) | See the section below |
| Pinpoint postings JSON | Direct ATS (layer 2), per-company | `GET https://{company}.pinpointhq.com/postings.json` | Documented public endpoint, no key | The configured organization name; original posting link kept | **Yes** (Milestone 8.1) | See the section below |
| Curated program registry | Layer 3, built in | Reads `backend/data/program_registry.json` from disk; no network | Owner-written facts with official source links | Each entry's official `source_url` | **Yes** (Milestone 8) | See the section below |
| Lever Postings API | Direct ATS (layer 2), per-company sites | `GET https://api.lever.co/v0/postings/{site}?mode=json` and `https://api.eu.lever.co/...` ([docs](https://github.com/lever/postings-api)) | Public postings API, no authentication | The configured organization name; original posting link kept | **Yes** (Milestone 3) | Published postings only. The authenticated Data API and candidate submission are never used |
| [`SuryaHarikrishnan/2027-internship-tracker`](https://github.com/SuryaHarikrishnan/2027-internship-tracker) | Reference only | — | Its software license doesn't clearly cover the aggregated listing data | — | **No, excluded** | Its listing data must not be imported. Its ideas may be read as a reference; no code is copied |
| [`pleasedodisturb/kestrel`](https://github.com/pleasedodisturb/kestrel) | Architectural reference only | — | AGPL-3.0 | — | No | No code copying unless licensing is separately reviewed and approved |

## Implemented Sources

### Tech Internship Discovery Feed (built in)

- **Source name / key:** `community_feed:zshah-tech-internships` (seeded by migration `726372d627b8`; can be renamed or disabled, not re-pointed)
- **Type / layer:** public structured feed, layer 1
- **Ingestion method:** one HTTPS GET of the JSON feed (about 1,000 postings, ~800 KB as of 2026-09-27)
- **Stable ID:** the feed's `id` (e.g. `greenhouse:<board>:<job>`, `workday:<tenant>:<path>`)
- **Mapped:** `company` → organization, `title`, `location`, `url` → application URL, `posted_at` → posted date (when it has a timezone), `remote: true` → remote (false isn't taken to mean on-site), `program: "Internship"` → internship (anything else → other). `first_seen_at`, `season`, `category`, `salary`, `skills`, `sponsorship`, `h1b_approvals`, and the rest stay in the raw payload only
- **Cross-source identity:** `zshah:<id>`; `greenhouse:<board>:<job>` when the ID has exactly that form (a link on a Greenhouse board host naming a different board is conflicting evidence and yields no identity; the EU Greenhouse hosts aren't matched, since discovery only calls the US Job Board API); `lever:<region>:<site>:<posting>` only when the posting URL is on `jobs.lever.co`/`jobs.eu.lever.co` with the same site and ID; `ashby:<board>:<posting>` only when the ID is exactly `ashby:<board>:<uuid>` **and** the posting URL is on `jobs.ashbyhq.com` with the same board and posting ID (Milestone 7, [ADR-013 §2](decisions/ADR-013-provider-enrichment-and-source-authority.md#2-ats-source-discovery)); a link with credentials or an explicit port proves nothing; the canonical URL
- **Completeness check:** the feed's `count` must equal the number of jobs, or the run fails
- **Conditional requests:** GitHub Pages returns `ETag`/`Last-Modified`; an unchanged feed answers 304 → `no_change`
- **Refresh:** manual (Sources page, API, or CLI). The feed itself updates about every 30 minutes

### Greenhouse boards

- **Source name / key:** `greenhouse:<board token>`; added on the Sources page from a board link (`https://boards.greenhouse.io/<board>` or `https://job-boards.greenhouse.io/<board>`) or a bare token
- **Stable ID:** the job `id`; identity `greenhouse:<board>:<id>` plus the canonical `absolute_url`
- **Mapped:** `title`, the configured organization name, `content` (entity-escaped HTML → plain text), `location.name`, `absolute_url`, `first_published` → posted date. `updated_at` is stored as the source update time and is never used as a posting date. Departments, offices, metadata, and the rest stay in the raw payload
- **Type:** `internship` when the title matches the shared internship title matcher (below), otherwise `other`: the API has no structured internship flag (Milestone 6; before that every Greenhouse posting was `other`)
- **Scope:** **Internships only** by default (title filter, below); **All postings** imports every published posting
- **Completeness check:** `meta.total` of the content-free list must equal the number of jobs; a duplicate job id or more than 10,000 jobs fails the run
- **Requests (Milestone 12, [ADR-022](decisions/ADR-022-large-board-greenhouse.md)):** a multi-request adapter that can still make one conditional request. A board with at most 500 stored jobs is fetched with one `?content=true` request carrying the stored ETag/Last-Modified (a 304 is `no_change` and keeps the validators). If that response is over the 20 MiB per-request cap (unchanged) or lists more than 500 jobs, or the source already stores more than 500 jobs (Anduril 2,457, SpaceX 2,665: `?content=true` is ~30 MB), the adapter reads `/jobs` (no content, the complete snapshot) and then `/jobs/<id>` only for internship-titled jobs, whatever the scope (scope **All postings** still imports every posting; non-internship ones have no description), reusing stored text while the `updated_at` that text belongs to is unchanged. A newly large board therefore costs at most one oversized download. Bounds per run: 100 detail attempts (failures count), 1 MiB per detail, 8 MiB of successful detail bytes (a failed read isn't counted but is capped at 1 MiB; at most 5 failures x 3 attempts), a 120 s deadline (a slow-drip response can still hold one request open up to the 20 s read timeout), 5 detail failures in total. A detail that isn't fetched keeps its stored text or has none and never closes or fails anything. A large board has no validators (always a full run)

### Lever sites

- **Source name / key:** `lever:<global|eu>:<site>`; added from `https://jobs.lever.co/<site>` (global), `https://jobs.eu.lever.co/<site>` (EU), or a site name plus region
- **Stable ID:** the posting `id`; identity `lever:<region>:<site>:<id>` plus the canonical `hostedUrl`
- **Mapped:** `text` → title, the configured organization name, `description` + `lists` + `additional` (HTML → plain text), `categories.allLocations`/`location`, `hostedUrl`, `workplaceType` (`onsite`/`remote`/`hybrid`; anything else → unknown), `createdAt` → posted date, and `categories.commitment` containing "intern" → internship (otherwise the shared title matcher decides, Milestone 6)
- **Scope:** **Internships only** by default (title filter, below); **All postings** imports every published posting

### Ashby boards (Milestone 6)

- **Source name / key:** `ashby:<board>`; added on the Sources page from a hosted board link (`https://jobs.ashbyhq.com/<board>`) or a bare board name. Only `jobs.ashbyhq.com` links are accepted; credentials, ports, other hosts, and malformed paths are refused. The link is parsed into the board name and never requested
- **Board names:** case-insensitive at the provider (verified 2026-10-01 against the public endpoint: three casings returned the same board), so they're lowercased and stored like Greenhouse tokens and Lever slugs, validated with the same slug pattern, and duplicates are detected on the lowercased name
- **Endpoint:** `https://api.ashbyhq.com/posting-api/job-board/<board>?includeCompensation=false` (Ashby's public Job Postings API; no key). The authenticated `job.list`/`jobPosting.list` API is never used
- **Listed postings only:** a job is imported only when `isListed` is exactly `true`. `false` jobs are dropped before processing, so a posting that becomes unlisted closes like a removed one on the next complete sync. A missing or non-boolean `isListed` (including the strings `"true"`/`"false"`) is an invalid item, never coerced: the run is partial and no unseen posting closes
- **Stable ID:** the job `id`; identity `ashby:<board>:<id>` plus the canonical `jobUrl`
- **Mapped:** `title`, the configured organization name, `descriptionPlain` (else `descriptionHtml` → plain text), `location` + `secondaryLocations[].location` joined with " · ", `jobUrl` (else `applyUrl`) as the application URL, `workplaceType` (`OnSite`/`Remote`/`Hybrid`) or, without it, `isRemote: true` → remote, `publishedAt` → posted date, and `employmentType: "Intern"` → internship (otherwise the shared title matcher decides). Department, team, address, and compensation stay out of scope
- **Scope:** **Internships only** by default; **All postings** imports every listed posting
- **Completeness check:** none; the endpoint has no total to compare

### SmartRecruiters companies (Milestone 8, ADR-014)

- **Source name / key:** `smartrecruiters:<company>`; added on the Sources page (or from a discovery suggestion) as a company identifier or an official `https://jobs.smartrecruiters.com/<company>` link. Only that host is accepted; other schemes and hosts, lookalikes, trailing dots, credentials, ports, empty path segments, and embedded whitespace or control characters are refused. The link is parsed into the identifier and never requested
- **Company identifiers:** case-insensitive at the provider (verified 2026-10-04), so they're lowercased and stored like the other providers' board names (`^[a-z0-9][a-z0-9_-]{0,63}$`)
- **Public data only:** SmartRecruiters documents its Posting API as public data that needs no authentication ([authentication guide](https://developers.smartrecruiters.com/docs/authentication)). The adapter calls only `https://api.smartrecruiters.com/v1/companies/<company>/postings?limit=100&offset=N&destination=PUBLIC` and `.../postings/<digits>`. Never INTERNAL destinations, candidate, application, or job administration APIs, and never a key
- **List walk:** pages of 100 until `totalFound`; at most 50 pages (5,000 postings). A walk that shifts (`totalFound` changes, an empty page early, a repeated ID, an oversized page) fails the run and closes nothing. A list item from another company is an item error
- **Detail:** the list has no description, so each admitted posting (under **Internships only**, internship titles only) needs one detail request, **at most 100 per run**. A stored detail is reused without a request when the posting's list entry is unchanged, so a steady-state run requests only the list pages plus a rotating refresh (each reused detail about once a week, from spare budget only; a failed refresh keeps the stored text). A detail that fails, names another posting or company, or exceeds the budget makes that posting an item error: the run is partial, nothing closes, and the posting's existing text is untouched; the next run retries. A first sync of a large internship board can take several (partial) runs
- **Stable ID:** the numeric posting `id`; identity `smartrecruiters:<company>:<id>` plus the posting page URL when it is the company's own `jobs.smartrecruiters.com/<company>/<id>` page
- **Mapped:** `name`, the configured organization name, the detail's `jobAd.sections` (company description, job description, qualifications, additional information) as plain text, `location.fullLocation`, `location.remote`/`hybrid` → remote/hybrid (otherwise unknown), `releasedDate` → posted date, `postingUrl` as the application URL, and `typeOfEmployment` `intern` or `experienceLevel` `internship` → internship (otherwise the shared title matcher). Only a fixed subset of provider keys is stored; the detail's `creator` (a person's name), custom fields, and referral links are never kept
- **Scope:** **Internships only** by default; **All postings** fetches every posting's detail (still capped at 100 per run)
- **Unknown company:** the API answers 200 with zero postings, so a misspelled identifier imports nothing; a company that renames its identifier closes its postings on the next complete run (closed, never deleted)

### Workable accounts (Milestone 8.1, ADR-015 §7)

- **Key:** `workable:<account>`; added as an account name or an `https://apply.workable.com/<account>` (or `<account>.workable.com`) link, parsed and never requested
- **Endpoint:** the documented jobs widget API `https://www.workable.com/api/accounts/<account>?details=true` (no key), which redirects to `apply.workable.com/api/v1/widget/accounts/<account>`; both hosts are allowlisted. One request per run; the response is the whole board
- **Stable ID:** the job `shortcode` (uppercased); identity `workable:<account>:<SHORTCODE>` plus the posting page URL, accepted only when its path names this account's own shortcode. Posted date = `published_on`; no deadline; remote/hybrid only when stated; `employment_type` `intern` → internship
- **Closure:** a 200 with a `jobs` list is a complete snapshot. Unknown account → 404 → failed run, nothing closes. A 200 with an empty list closes everything (same accepted limitation as other single-request providers)

### Pinpoint companies (Milestone 8.1, ADR-015 §7)

- **Key:** `pinpoint:<company>`; added as the company subdomain label or an `https://<company>.pinpointhq.com/...` link
- **Endpoint:** the documented `https://<company>.pinpointhq.com/postings.json` (no key, no pagination). The network boundary allows exactly one DNS label under `pinpointhq.com` (`ALLOWED_HOST_PATTERN`); posting URLs are accepted only on the same company's subdomain
- **Stable ID:** the posting `id`; identity `pinpoint:<company>:<id>` plus the posting URL. No posted date exists in the API, so none is set; `deadline_at` is parsed but, like every ATS deadline field today, not written to the canonical opportunity (only the registry writes deadlines, ADR-014 §6); `workplace_type` → remote mode; `employment_type` `internship` → internship
- **Closure:** as Workable; unknown company → 404

### Direct Source Catalog (Milestone 8.1, ADR-015 §6)

`backend/data/direct_source_catalog.json`: officially verified board configurations (organization, provider, identifier, careers URL, evidence, verification date, tags). Configuration only, never listing data or another tracker's data. The Sources page's **Verified Direct Sources** adds selected entries (1–25 at a time, Internships only, never synced on add). 90 entries: 36 verified 2026-10-05 ([direct-company-source-matrix.md](research/direct-company-source-matrix.md)) and 54 verified 2026-10-06 (28 in [direct-source-expansion-2026-10-06.md](research/direct-source-expansion-2026-10-06.md), which also classifies Teamtailor, Rippling, Personio, Breezy, Recruitee, JazzHR, BambooHR, and Jobvite; no new adapter passed the value bar; 26 in [feed-dependence-pareto-2026-10-06.md](research/feed-dependence-pareto-2026-10-06.md)). To add an entry: verify ownership from the company's careers page and/or the provider's documented API, record the evidence, keep the identifier in canonical (lowercase) form; the loader rejects anything else.

Production status (2026-10-06): 19 entries were activated; the Anduril and SpaceX entries failed with "response too large" (over the 20 MiB response cap) in production. Milestone 12 ([ADR-022](decisions/ADR-022-large-board-greenhouse.md)) adds the large-board path that fixes them in code; they stay unactivated (Anduril disabled) until a release and an owner-approved activation ([operations.md](operations.md#milestone-9-11-release-train-measurements-2026-10-06)).

### Retiring a source and starting without the feed (Milestone 8.2, ADR-016)

`python -m app.cli retire-source SOURCE [--apply]` closes a source's open records through the same closure path a complete snapshot uses (closed, never deleted; the ADR-013 §5 fallback moves canonical content to the next remaining source; opportunities with another active source stay open; curated opportunities keep their content (and close if no active source remains), manual opportunities and application tracking are untouched), then disables the source, atomically. It is a dry run unless `--apply`. `python -m app.cli bootstrap-sources` adds Direct Source Catalog entries to a new installation (same path as the catalog add API, at most 100 enabled direct sources) so the community feed isn't needed. Procedure: [operations.md](operations.md#retiring-a-source-and-feed-free-start-implemented-milestone-82-adr-016). Decision: [ADR-016](decisions/ADR-016-source-retirement-and-feed-free-bootstrap.md).

### Opportunity type (Milestone 6)

One shared rule for every adapter ([ADR-012 §13](decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md#13-opportunity-type)): a structured provider field that says intern wins (Lever `commitment`, Ashby `employmentType`, the feed's `program`); otherwise the internship title matcher below; otherwise `other`. Type is a display and discovery aid, never eligibility. Because this changes the normalized form of existing imported postings whose titles match, the first sync after the release reports them as `updated` once; nothing is closed or lost, and since title and description are unchanged it doesn't make any requirement review stale.

### Board scope: internships only (every ATS board)

Adding a company board shouldn't flood the catalog with full-time jobs ([ADR-010 §10](decisions/ADR-010-fit-scoring-v1.md#10-ats-scope-internships-only-by-default)). Each ATS source has a scope, chosen when it's added and changeable on the Sources page:

- **Internships only** (default): a posting is kept only when its **title** contains, as a whole word (case- and Unicode-normalized), `intern`, `interns`, `internship(s)`, `co-op(s)`, `co op`, `coop(s)`, `apprentice(s)`, or `apprenticeship(s)`. Descriptions are never searched, because full-time postings often mention internship programs. `student`, `new grad`, `junior`, and `entry level` don't count. Limitations: an internship titled without those words is filtered, and a title such as "Internship Program Manager" is kept; choose **All postings** for boards where that matters.
- **All postings:** everything the board publishes.

Excluded postings count as **Filtered** in the run (`fetched` = provider items, `filtered` = excluded by scope, `normalized` = admitted to the pipeline) and are never processed. Changing the scope clears the source's `ETag`/`Last-Modified`, so the next sync fetches the full board instead of accepting a `304`: switching to internships-only closes previously imported postings that are now filtered (through the normal closure rule; nothing is deleted), and switching back reopens them. Items that fail validation have no trustworthy title, so they stay invalid (making the run partial) rather than filtered. Boards added before Milestone 4 were migrated to **All postings**, so the upgrade itself never closes anything. The built-in discovery feed is internship-focused already and is always **All postings**.

The opportunity list also filters by the provider's posted date (`posted_within=7|30|90`, **Posted** on the Opportunities page); postings with no posted date match only when the filter is off. Old is never treated as closed (ADR-015).

### Curated program registry (Milestone 8, ADR-014)

A built-in source (`curated_registry`, identifier `program-registry`) imports `backend/data/program_registry.json`: public facts about named programs (research, fellowships, summer programs), each with an official `source_url` and a `last_verified` date. It reads the file from disk and never touches the network. It can be disabled but not created, re-pointed, or filtered. Last re-verified 2026-10-06 (Tech Interactive, DOE SULI Summer 2027, MIT PRIMES; dates the official page calls tentative say so in the summary).

- **Schema:** `{"schema_version": 1, "programs": [...]}`, strict (unknown keys rejected). An entry has `slug`, `cycle` (`2027`, `2027-summer`), `title`, `organization`, `opportunity_type`, `application_url` (or null), `source_url`, optional `location` / `remote_mode`, `verified` (`open_date`, `deadline`, `start_date`, `end_date`), `typical_open_window` / `typical_close_window` (free text), `verify_by`, `eligibility_summary`, an owner-written paraphrased `description`, and `last_verified`. Links are plain https (no credentials, no port). A malformed file or a repeated `(slug, cycle)` fails the run and changes nothing; a malformed entry is an item error (partial run, nothing closes).
- **Verified vs typical:** a date goes in `verified` only when the official page states it as firm for that cycle; dates the program calls tentative, pending approval, or subject to change go in the description or a typical window. Only `verified` dates become the opportunity's deadline / start / end. A typical window ("February") is display text and never a date, so deadline sorting, filters, and eligibility never see it.
- **`verify_by`:** from that date the opportunity shows "Needs date verification" (also the `needs_date_verification` list filter). It never closes or hides anything.
- **Updating:** a reviewed pull request to the file, then a sync (manual or scheduled; the registry syncs with the ATS tier, before the discovery feed). An unchanged entry is a no-op, an edited entry updates the same opportunity, a new cycle is a new opportunity, and a removed entry is closed (not deleted).
- **Identity:** `curated:<slug>:<cycle>` only. There is deliberately no URL identifier, so a feed posting with the same link never merges with a program.
- **Contents:** 24 programs (13 from Milestone 8; 11 for the 2027 cycle added 2026-10-06, [research](research/curated-program-expansion-2027.md)). Programs open only to enrolled undergraduates are left out until the owner can use them.
- **Owner edits win:** editing a registry opportunity in the app marks it curated; later registry changes update its source record but never its fields. Requirement candidates from the description and eligibility summary stay pending.

### Manual entry

Opportunities added through the app keep a `manual` source record without an external ID. They're curated from the start, never closed by a sync, and not matched by identifiers.

## Source authority (Milestone 7)

Canonical fields (title, organization, description, application URL, location, remote mode, posted date, opportunity type) have exactly one automated owner per opportunity: the highest-authority active automated source record ([ADR-013 §1](decisions/ADR-013-provider-enrichment-and-source-authority.md#1-automated-source-authority)).

| Rank | `source_type` | |
|---|---|---|
| 0 | `ats` (Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Pinpoint) | the original posting, with its text |
| 1 | `public_feed` (the discovery feed) | discovery metadata about someone else's posting |
| 2 | anything else | |

Ties within a rank: earliest `first_seen_at`, then record ID — so two boards naming one posting never alternate.

The owner's fields are rewritten from its normalized output when its own item changes, it reactivates, it first attaches through deduplication and outranks the current owner (**takeover**: a board added after the feed), or the previous owner closes and it's the next owner (**fallback**: re-derived from the new owner's own *stored* raw item through its adapter's per-item normalizer, no fetch, in the same run as the closure, [ADR-013 §5](decisions/ADR-013-provider-enrichment-and-source-authority.md#5-fallback-when-a-direct-ats-source-closes)). The discovery feed never supplies a description, so a feed owner taking over keeps the last known posting text instead of erasing it; every other field is restored from the feed. Non-owners only update their own source record; unchanged items skip canonical work entirely.

A curated opportunity (`manually_curated_at`) is never rewritten by any sync, owner or not (ADR-008 §8) — above all of the above. The owner can discard their edits with **Revert to source**, which re-derives the content from the authoritative active record the same way ([ADR-017 §4](decisions/ADR-017-owner-opportunity-decisions.md)). A hidden opportunity (`dismissed_at`) is not curated: syncs keep updating it and never un-hide it or re-import it as new.

## Source coverage and discovery (Milestone 7)

`GET /api/sources/discovery` derives coverage metrics and board suggestions on read from active discovery-feed records already in the database (`external_id` and the stored posting URL). It makes **zero network calls** and stores nothing ([ADR-013 §2](decisions/ADR-013-provider-enrichment-and-source-authority.md#2-ats-source-discovery)).

A feed record proves a board only through the same `provider_identity` function the feed adapter uses for deduplication, so discovery and dedup can never disagree:

- **Greenhouse:** ID exactly `greenhouse:<board>:<digits>`. A link on a Greenhouse board host naming a different board is conflicting evidence and yields nothing. The EU Greenhouse hosts aren't suggested, because the adapter only calls the US Job Board API.
- **Lever:** ID exactly `lever:<site>:<uuid>` **and** a matching `https` posting link on `jobs.lever.co`/`jobs.eu.lever.co` (same site and ID; the host decides the region, never guessed).
- **Ashby:** ID exactly `ashby:<board>:<uuid>` **and** a matching `https` posting link on `jobs.ashbyhq.com` (same board and posting ID).
- **SmartRecruiters (Milestone 8):** ID exactly `smartrecruiters:<company>:<digits>` **and** a matching `https` posting link on `jobs.smartrecruiters.com` (`/<company>/<id>` or `/<company>/<id>-<title-slug>`, company compared case-insensitively). Never inferred from the company name.

A link with credentials or an explicit port proves nothing; hosts are compared exactly. Workday, Oracle, Rippling, Workable, and every other provider named in feed IDs are **counted only** (Workable and Pinpoint have adapters since Milestone 8.1, but discovery doesn't suggest them from feed IDs) (by a fixed list of known ID prefixes; anything else is `other`) — never fetched, scraped, or reverse-engineered (research only, no behavior change: [m13-workday-oracle-provider-gate.md](research/m13-workday-oracle-provider-gate.md) re-classifies Workday, Oracle, and 14 other provider families). The feed's company label is only a *suggested display name*: when feed rows for one board disagree, the most common label wins (ties alphabetically) and the suggestion is flagged ambiguous. Company names are never identity.

Discovery only suggests. `POST /api/sources/discovery/add` (CSRF-protected) creates sources only when the owner selects suggestions and submits: at most 25 per request, validated all-or-nothing; the client sends only `kind`, `identifier`, and `region`, and the server re-derives the current suggestion set and refuses anything not in it. Already-configured suggestions are skipped and reported, never duplicated (the existing unique constraint on `(kind, identifier, region)` is the final guard). New sources default to **Internships only**. Creating a source never syncs it — the owner syncs with the existing controls.

Which boards are enabled in production, and when each batch was added: [deployment.md](deployment.md), [operations.md](operations.md), [CHANGELOG.md](../CHANGELOG.md), and `GET /api/sources` (the live source list).

The Action Inbox ([ADR-020](decisions/ADR-020-action-inbox.md)) reads sources only to list unhealthy ones (derived health, as on the Sources page) and reuses the list's "open" rule (`discovery.is_open`, an export of the existing availability filter). Ingestion behavior is unchanged.

## Common Behavior

- **Network safety:** HTTPS to the allowlisted provider hosts only (`ALLOWED_HOSTS` in `ingestion/http.py`: the feed host, Greenhouse, Lever global/EU, Ashby, SmartRecruiters, `www.`/`apply.workable.com`, plus exactly one label under `pinpointhq.com`), public addresses only, 5 s connect / 20 s read timeouts, ≤ 3 redirects (each re-checked), ≤ 20 MiB responses (decoded bytes, so a compression bomb is capped too; a caller may only tighten the cap, e.g. 1 MiB per Greenhouse detail), ≤ 3 attempts (429/5xx/timeouts; `Retry-After` honored up to 30 s), a descriptive `User-Agent`. User-entered links are parsed into identifiers and never requested.
- **Deduplication:** same source + external ID first, then exact identifiers; no fuzzy matching. Conflicting identities are recorded as errors and nothing is merged ([ADR-008 §7](decisions/ADR-008-opportunity-ingestion-and-deduplication.md#7-deduplication-order)).
- **Failure behavior:** fetch, format, and completeness failures fail the run without changing data. One bad item makes the run `partial` and is recorded; other items still import. Only a complete successful snapshot closes postings it no longer contains. Closed postings reopen if they return.
- **Fit:** adapters never score. Imported postings are scored by the shared evaluation step like any other opportunity ([scoring.md](scoring.md)); feed hints such as sponsorship, H-1B counts, or skill tags stay discovery metadata in the raw payload and affect neither eligibility nor fit.
- **Requirements:** imported opportunities start `unassessed` (so at least `needs_verification`) until the owner reviews them. Nothing in a source becomes a hard requirement automatically. Since Milestone 6, new and materially changed postings get deterministic requirement *suggestions* that change nothing until the owner accepts them ([ADR-012](decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)). Suggestions need posting text: the discovery feed has no description field, so its postings get none (production, 2026-10-02: 0 suggestions over 1,193 feed opportunities); Greenhouse, Lever, and Ashby boards include descriptions. Since Milestone 7, a feed posting that a board source takes over or falls back onto (below) gets suggestions from the board's own description on that same run.
- **Descriptions:** stored and displayed as plain text only. The original posting link is always kept.

## Adapter Boundary

Implemented in `backend/app/ingestion/adapters/` ([ADR-008 §2](decisions/ADR-008-opportunity-ingestion-and-deduplication.md#2-adapter-boundary)): each adapter has a `url(source)` built from its hard-coded host and a `parse(payload, source)` that validates the top level and returns `NormalizedOpportunity` items or per-item errors. Adapters don't implement scoring, eligibility, schema, persistence, or deduplication.

## Planned Sources

| Source | Layer | Status | Notes |
|---|---|---|---|
| University/research programs | 3 | Partly implemented | A curated subset ships in the program registry (Milestone 8); automated per-university sources are not built |
| Government / nonprofit STEM programs, fellowships | 3 | Partly implemented (registry only) | Often high-school or incoming-freshman eligible |
| Selected company career pages | 4 | Research (ADR-015 §8) | No first-party source passed the gate in M8.1; Netflix/Microsoft (Eightfold sitemap + JSON-LD) are the top YELLOW candidates; provenance would be `career_page` |

## Required Definition per Source

Before a source moves to **Implemented**, document:

- **Source name:** a unique identifier used in records and logs
- **Source type / layer:** feed, ATS, program page, company site, manual, etc.
- **Ingestion method:** API, feed, HTML parse, browser automation, manual
- **License / terms:** whether use is permitted, and attribution
- **Stable ID behavior:** which external ID is used and which cross-source identifiers are derived
- **Dates captured:** posted/published dates, start date, deadline
- **Refresh cadence:** how often it runs
- **Failure behavior:** timeouts, rate limits, malformed records, partial results
- **Deduplication strategy:** external ID first, then exact identifiers

## Maintenance

Update this file whenever a source is added, removed, or changes status, and update [PROJECT_STATE.md](../PROJECT_STATE.md) → Active Opportunity Sources to match.
