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

Last reviewed: 2026-10-02 (Ashby added; earlier rows 2026-09-27).

| Source | Role | API / docs | License / usage basis | Attribution | Implemented? | Notes |
|---|---|---|---|---|---|---|
| zshah101 Summer/Fall Tech Internships feed | Broad discovery (layer 1), built in | Public JSON feed: `https://zshah101.github.io/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships/api/jobs.json` ([repository](https://github.com/zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships)) | Repository is MIT-licensed. We consume only the published API; none of its code is copied | Listed here and shown as "Tech Internship Discovery Feed" on every imported record; each record keeps the original posting link | **Yes** (Milestone 3) | Factual listing metadata; external source links retained. Source-provided sponsorship, H-1B, skill, and category classifications are **not** hard eligibility; they stay in the raw payload only |
| Greenhouse Job Board API | Direct ATS (layer 2), per-company boards | `GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true` ([docs](https://developers.greenhouse.io/job-board.html)) | Public GET endpoints, no authentication, intended for publishing a company's board | The configured organization name; original posting link kept | **Yes** (Milestone 3) | Published board data only. The application-submission endpoint is never used |
| Ashby Job Postings API | Direct ATS (layer 2), per-company hosted job boards | `GET https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=false` ([docs](https://developers.ashbyhq.com/docs/public-job-posting-api)) | Public GET endpoint, no authentication, intended for publishing a company's hosted job board | The configured organization name; original posting link (`jobUrl`) kept | **Yes** (Milestone 6) | Listed postings (`isListed: true`) only. The authenticated Ashby API and application submission are never used |
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
- **Cross-source identity:** `zshah:<id>`; `greenhouse:<board>:<job>` when the ID has exactly that form; `lever:<region>:<site>:<posting>` only when the posting URL is on `jobs.lever.co`/`jobs.eu.lever.co` with the same site and ID; the canonical URL
- **Completeness check:** the feed's `count` must equal the number of jobs, or the run fails
- **Conditional requests:** GitHub Pages returns `ETag`/`Last-Modified`; an unchanged feed answers 304 → `no_change`
- **Refresh:** manual (Sources page, API, or CLI). The feed itself updates about every 30 minutes

### Greenhouse boards

- **Source name / key:** `greenhouse:<board token>`; added on the Sources page from a board link (`https://boards.greenhouse.io/<board>` or `https://job-boards.greenhouse.io/<board>`) or a bare token
- **Stable ID:** the job `id`; identity `greenhouse:<board>:<id>` plus the canonical `absolute_url`
- **Mapped:** `title`, the configured organization name, `content` (entity-escaped HTML → plain text), `location.name`, `absolute_url`, `first_published` → posted date. `updated_at` is stored as the source update time and is never used as a posting date. Departments, offices, metadata, and the rest stay in the raw payload
- **Type:** `internship` when the title matches the shared internship title matcher (below), otherwise `other`: the API has no structured internship flag (Milestone 6; before that every Greenhouse posting was `other`)
- **Scope:** **Internships only** by default (title filter, below); **All postings** imports every published posting
- **Completeness check:** `meta.total` must equal the number of jobs

### Lever sites

- **Source name / key:** `lever:<global|eu>:<site>`; added from `https://jobs.lever.co/<site>` (global), `https://jobs.eu.lever.co/<site>` (EU), or a site name plus region
- **Stable ID:** the posting `id`; identity `lever:<region>:<site>:<id>` plus the canonical `hostedUrl`
- **Mapped:** `text` → title, the configured organization name, `description` + `lists` + `additional` (HTML → plain text), `categories.allLocations`/`location`, `hostedUrl`, `workplaceType` (`onsite`/`remote`/`hybrid`; anything else → unknown), `createdAt` → posted date, and `categories.commitment` containing "intern" → internship (otherwise the shared title matcher decides, Milestone 6)
- **Scope:** **Internships only** by default (title filter, below); **All postings** imports every published posting

### Ashby boards (Milestone 6)

- **Source name / key:** `ashby:<board>`; added on the Sources page from a hosted board link (`https://jobs.ashbyhq.com/<board>`) or a bare board name. Only `jobs.ashbyhq.com` links are accepted; credentials, ports, other hosts, and malformed paths are refused. The link is parsed into the board name and never requested
- **Board names:** case-insensitive at the provider (verified 2026-10-01 against the public endpoint: three casings returned the same board), so they're lowercased and stored like Greenhouse tokens and Lever slugs, validated with the same slug pattern, and duplicates are detected on the lowercased name
- **Endpoint:** `https://api.ashbyhq.com/posting-api/job-board/<board>?includeCompensation=false` (Ashby's public Job Postings API; no key). The authenticated `job.list`/`jobPosting.list` API is never used
- **Listed postings only:** a job is imported only when `isListed` is exactly `true` (or absent; every observed job carries it). Unlisted jobs are dropped before processing, so a posting that becomes unlisted closes like a removed one on the next complete sync
- **Stable ID:** the job `id`; identity `ashby:<board>:<id>` plus the canonical `jobUrl`
- **Mapped:** `title`, the configured organization name, `descriptionPlain` (else `descriptionHtml` → plain text), `location` + `secondaryLocations[].location` joined with " · ", `jobUrl` (else `applyUrl`) as the application URL, `workplaceType` (`OnSite`/`Remote`/`Hybrid`) or, without it, `isRemote: true` → remote, `publishedAt` → posted date, and `employmentType: "Intern"` → internship (otherwise the shared title matcher decides). Department, team, address, and compensation stay out of scope
- **Scope:** **Internships only** by default; **All postings** imports every listed posting
- **Completeness check:** none; the endpoint has no total to compare

### Opportunity type (Milestone 6)

One shared rule for every adapter ([ADR-012 §13](decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md#13-opportunity-type)): a structured provider field that says intern wins (Lever `commitment`, Ashby `employmentType`, the feed's `program`); otherwise the internship title matcher below; otherwise `other`. Type is a display and discovery aid, never eligibility. Because this changes the normalized form of existing imported postings whose titles match, the first sync after the release reports them as `updated` once; nothing is closed or lost, and since title and description are unchanged it doesn't make any requirement review stale.

### Board scope: internships only (Greenhouse, Lever, and Ashby)

Adding a company board shouldn't flood the catalog with full-time jobs ([ADR-010 §10](decisions/ADR-010-fit-scoring-v1.md#10-ats-scope-internships-only-by-default)). Each Greenhouse, Lever, or Ashby source has a scope, chosen when it's added and changeable on the Sources page:

- **Internships only** (default): a posting is kept only when its **title** contains, as a whole word (case- and Unicode-normalized), `intern`, `interns`, `internship(s)`, `co-op(s)`, `co op`, `coop(s)`, `apprentice(s)`, or `apprenticeship(s)`. Descriptions are never searched, because full-time postings often mention internship programs. `student`, `new grad`, `junior`, and `entry level` don't count. Limitations: an internship titled without those words is filtered, and a title such as "Internship Program Manager" is kept; choose **All postings** for boards where that matters.
- **All postings:** everything the board publishes.

Excluded postings count as **Filtered** in the run (`fetched` = provider items, `filtered` = excluded by scope, `normalized` = admitted to the pipeline) and are never processed. Changing the scope clears the source's `ETag`/`Last-Modified`, so the next sync fetches the full board instead of accepting a `304`: switching to internships-only closes previously imported postings that are now filtered (through the normal closure rule; nothing is deleted), and switching back reopens them. Items that fail validation have no trustworthy title, so they stay invalid (making the run partial) rather than filtered. Boards added before Milestone 4 were migrated to **All postings**, so the upgrade itself never closes anything. The built-in discovery feed is internship-focused already and is always **All postings**.

### Manual entry

Opportunities added through the app keep a `manual` source record without an external ID. They're curated from the start, never closed by a sync, and not matched by identifiers.

## Common Behavior

- **Network safety:** HTTPS to the five allowlisted API hosts only, public addresses only, 5 s connect / 20 s read timeouts, ≤ 3 redirects (each re-checked), ≤ 20 MB responses, ≤ 3 attempts (429/5xx/timeouts; `Retry-After` honored up to 30 s), a descriptive `User-Agent`. User-entered links are parsed into identifiers and never requested.
- **Deduplication:** same source + external ID first, then exact identifiers; no fuzzy matching. Conflicting identities are recorded as errors and nothing is merged ([ADR-008 §7](decisions/ADR-008-opportunity-ingestion-and-deduplication.md#7-deduplication-order)).
- **Failure behavior:** fetch, format, and completeness failures fail the run without changing data. One bad item makes the run `partial` and is recorded; other items still import. Only a complete successful snapshot closes postings it no longer contains. Closed postings reopen if they return.
- **Fit:** adapters never score. Imported postings are scored by the shared evaluation step like any other opportunity ([scoring.md](scoring.md)); feed hints such as sponsorship, H-1B counts, or skill tags stay discovery metadata in the raw payload and affect neither eligibility nor fit.
- **Requirements:** imported opportunities start `unassessed` (so at least `needs_verification`) until the owner reviews them. Nothing in a source becomes a hard requirement automatically. Since Milestone 6, new and materially changed postings get deterministic requirement *suggestions* that change nothing until the owner accepts them ([ADR-012](decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)).
- **Descriptions:** stored and displayed as plain text only. The original posting link is always kept.

## Adapter Boundary

Implemented in `backend/app/ingestion/adapters/` ([ADR-008 §2](decisions/ADR-008-opportunity-ingestion-and-deduplication.md#2-adapter-boundary)): each adapter has a `url(source)` built from its hard-coded host and a `parse(payload, source)` that validates the top level and returns `NormalizedOpportunity` items or per-item errors. Adapters don't implement scoring, eligibility, schema, persistence, or deduplication.

## Planned Sources

| Source | Layer | Status | Notes |
|---|---|---|---|
| University/research programs | 3 | Planned | Often seasonal and deadline-driven; start dates matter for time-aware eligibility |
| Government / nonprofit STEM programs, fellowships | 3 | Planned | Often high-school or incoming-freshman eligible |
| Selected company career pages | 4 | Planned | Stable IDs may be missing; would need an exact-URL identity |

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
