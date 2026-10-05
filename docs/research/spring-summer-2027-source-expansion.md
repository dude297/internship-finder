# Spring/Summer 2027 Source Expansion (M8 research, 2026-10-04)

> Local examples use the San Francisco Bay Area as an example region; adapters would be region-agnostic. Claims were checked on 2026-10-04 and decay: re-verify terms, robots.txt, API docs and every company-to-ATS mapping before building anything. Volunteer sources are covered separately in `volunteer-sources-2027.md` (Milestone 7.1).

Research only. No code, accounts, API-key signups, or form submissions were made. The only network contact beyond reading docs was anonymous GETs of SmartRecruiters' public Posting API (`/v1/companies/smartrecruiters/postings?limit=1` and that posting's detail) to confirm the documented public access and the response shape.

> **Updated 2026-10-04 (after the Milestone 7 / 7.1 release).** Milestone 7 (provider enrichment and source authority, [ADR-013](../decisions/ADR-013-provider-enrichment-and-source-authority.md)) and Milestone 7.1 (volunteer type) are released. Production now has **20 direct ATS boards** (13 Greenhouse, 2 Lever, 5 Ashby), and description coverage is **22.4% (294 / 1,313 open opportunities)**. Production numbers below that predate activation are labelled *historical*. The SmartRecruiters classification was corrected against SmartRecruiters' own authentication guide (§5.2). The decisions taken from this research are recorded in ADR-014 (Milestone 8, `docs/decisions/ADR-014-structured-source-expansion-and-program-registry.md`).

Evidence labels: **[official]** = fetched from the vendor/agency page cited; **[3rd-party]** = vendor-adjacent blog/scraper listing, not authoritative; **[unverified]** = could not confirm.

## 1. Summary

### The key finding

The owner is a high-school senior graduating June 2027 and entering college fall 2027. Nearly every program that is *structured and API-accessible* targets people who are **already enrolled** (or recent graduates), and nearly every *high-school* program targets **rising juniors/seniors**, i.e. students who will still be in high school in summer 2027. The owner falls into a gap:

- HS-only programs for Summer 2027 mostly exclude "students graduating high school that summer" (UCSC SIP states this [3rd-party]; Stanford SIMR 2026 required class of 2026/2027 at application time [3rd-party], so the owner's cohort was eligible only for the 2026 cycle that has closed).
- Federal intern programs (DOE SULI/CCI, NSF REU, NASA Pathways) require current college enrollment or a degree. NASA OSTEM requires 16+ and "enrolled at an accredited U.S. institution" [official: nasa.gov/learning-resources/internships]. Whether an admitted-but-not-yet-matriculated freshman counts is **unverified** and must be checked per posting.
- Company internships (e.g. NVIDIA general internship targets class-of-2028 first-years and class-of-2027 second-years [3rd-party]) usually require current university enrollment.

So the realistic Summer 2027 targets are: (a) bridge/incoming-freshman and "Spring 2027 part-time/remote" roles at startups and mid-size firms that don't gate on enrollment; (b) programs explicitly open to "recent high-school graduates" (e.g. NLR-SLAC Pathway Summer School: "high school students and recent high school graduates" in the Bay Area [3rd-party search summary of orise.orau.gov]); (c) community-college/dual-enrollment-adjacent paths (CCI requires community-college enrollment, so only if the owner dual-enrolls); (d) local volunteer/research-assistant roles posted on small-org boards.

Therefore the best investment is **breadth of eligibility-aware discovery plus a curated program calendar**, not a large number of new ATS adapters. The existing requirement-text pipeline (ADR-012) is what turns breadth into usefulness.

### Top 10 sources (value for this student, in order)

1. **Curated HS / early-college program registry** (SIMR, UCSC SIP, LBNL Experiences in Research, NLR-SLAC Pathway, MIT RSI/PRIMES, REU directory entries, etc.) as repo-committed public data, zero network. Highest relevance, zero adapter risk.
2. **More Greenhouse/Lever/Ashby boards** via the existing ADR-013 discovery, plus a short owner-vetted seed list of Bay Area hardware/AI/robotics startups. Already built; M8 adds only a seed list and docs.
3. **SmartRecruiters Posting API** (public, keyless, JSON, paginated). A fourth structured ATS adapter on the same pattern.
4. **USAJOBS Search API** (free key, owner-held; `HiringPath=student`; structured deadlines/requirements/duties text). Needs a secret, so it is owner-gated.
5. **NSF REU Directory** (manual/curated; no feed; ETAP robots.txt disallows all crawling).
6. **NASA OSTEM via STEM Gateway** (manual calendar entry; no feed found; Summer 2027 deadline ~Feb 26-Mar 1, 2027).
7. **DOE SULI/CCI** (manual calendar; college-only; Spring 2027 closes 2026-09-30).
8. **Recruitee / Breezy / Personio public feeds** (small-company boards; documented-or-unofficial, see survey).
9. **Workday-hosted semiconductor/lab postings** reached only via the existing discovery feed's links (no Workday scraping).
10. **National-lab career portals** (LBNL/LLNL/SLAC/ANL/ORNL/NREL/Sandia): link-out only; most are Workday/custom.

### Production evidence

**Current (2026-10-04, after M7 activation):** 1,313 open opportunities; 20 direct ATS boards active (13 Greenhouse, 2 Lever, 5 Ashby); 294 / 1,313 (22.4%) have descriptions. The feed still names about 40 SmartRecruiters postings that no adapter can enrich.

**Historical (read-only `source-coverage`, 2026-10-04, before any ATS source was added):** the discovery feed's 1,113 open postings by apply-link provider: Workday 601, Greenhouse 207, **Oracle (Cloud HCM) 147**, Ashby 58, **SmartRecruiters 40**, Lever 28, other 13, Rippling 11, Workable 8. Greenhouse/Lever/Ashby (288 enrichable) are already covered by ADR-013 discovery. This supports SmartRecruiters as the next ATS adapter: once it exists, discovery could map those 40 feed postings exactly as it does for the other three. Oracle Cloud HCM is the second-largest unsupported provider and was **not researched here**. Follow-up task: check whether its candidate-experience REST endpoints are documented for anonymous public use; if not, Oracle stays link-out like Workday.

### Recommendation

Build **three adapters/features in M8**: (T1) curated program registry import, (T2) SmartRecruiters adapter, (T3) USAJOBS adapter (owner-gated, can slip). Write **ADR-014** scoped to "additional structured sources and the curated program registry" with an explicit exclusion list (Workday, iCIMS, Eightfold, Phenom, SuccessFactors, Taleo, ETAP, STEM Gateway, any HTML/browser scraping). Do not add Workable, Rippling, Jobvite, Teamtailor, BambooHR adapters. Recruitee/Breezy/Personio are Tier 2 behind a go/no-go check of each vendor's terms.

## 2. Method

- Read local context: ADR-013 (ATS ranks 0, `public_feed` 1, others 2; discovery derived on read; exact IDs only), ADR-005 (layers; HTML/browser last), `docs/sources.md`, `backend/app/ingestion/http.py`. Current `ALLOWED_HOSTS`: `zshah101.github.io`, `boards-api.greenhouse.io`, `api.lever.co`, `api.eu.lever.co`, `api.ashbyhq.com`. Adapters present: `ashby`, `community_feed`, `greenhouse`, `lever`.
- Web search + official-page fetches on 2026-10-04. Where a vendor page did not render or a fact came only from scraper/blog sites, it is labelled **[3rd-party]** or **[unverified]**.
- Rule applied to every candidate: no card, no paid API, no CAPTCHA/bot-control bypass, no browser automation, no Workday scraping, respect robots/terms. A source that needs a *free* key held by the owner is allowed but flagged (secret handling, ADR needed).
- Limits: NASA STEM Gateway and several vendor docs returned empty/JS-only content to the fetcher; those claims are unverified. Company-to-ATS mappings for semiconductor firms are mostly from [3rd-party] pages and must be re-checked by loading each careers page once by hand before configuring anything.

## 3. Season calendar (Spring 2027 and Summer 2027)

Dates marked "typical" are inferred from prior cycles and are **unverified for 2027**. Today is 2026-10-04.

| Program | Season | Opens | Closes / deadline | Owner-eligible? | Evidence |
|---|---|---|---|---|---|
| NASA OSTEM internships | Spring 2027 | open (Aug-Sep 2026) | 2026-09-14 11:59 pm ET (already closed) | Unclear (needs enrollment) | [3rd-party] opportunitiesforyouth.org; nasa.gov page lists only Summer/Fall |
| NASA OSTEM internships | Summer 2027 | ~Dec 2026-Jan 2027 (unverified) | 2027-03-01 11:59 pm ET per NASA; one 3rd-party says 2027-02-26 | Unclear | [official] nasa.gov/learning-resources/internships |
| NASA OSTEM internships | Fall 2027 | unverified | 2027-05-24 | Likely yes if enrolled | [official] same page |
| NASA Pathways | rolling | USAJOBS postings | per posting | No (15 semester hours + 2.9 GPA required) | [official] same page |
| DOE SULI / CCI | Spring 2027 | Aug 2026 | 2026-09-30 5:00 pm ET (closes in 26 days) | No (college/community-college/recent grad) | [official] energy.gov Spring 2027 article |
| DOE SULI / CCI | Summer 2027 | typical Oct-Nov 2026 | typical Jan 2027 (unverified) | No | portal: science.osti.gov/wdts |
| NSF REU sites | Summer 2027 | typical Nov 2026-Jan 2027 | typical Jan-Mar 2027 per site | No (undergrads pursuing associate/bachelor's) | [official] nsf.gov REU students page |
| Stanford SIMR | Summer 2027 | typical Dec-Jan | typical mid/late Feb (2026: Feb 21) | Probably no (current jr/sr at application) | [3rd-party] SIMR 2026 info doc |
| UCSC Science Internship Program | Summer 2027 | typical Feb 1 | typical late Feb | No ("graduating HS that summer" excluded) | [3rd-party] |
| LBNL Experiences in Research | Summer 2027 | typical Jan-Feb | 2026 cycle: 2026-03-23 | Probably no (10th-12th grade enrolled N. California) | [3rd-party] k12education.lbl.gov |
| NLR-SLAC Pathway Summer School | Summer 2027 | unverified | 2026 dates ran Jun 22-Jul 31; apps closed | Possibly yes (includes "recent high school graduates") | [3rd-party] orise.orau.gov |
| MIT RSI | Summer 2027 | fall 2026 | typical early-mid Dec 2026 | No (juniors only) | [3rd-party] |
| MIT PRIMES | 2027 cycle | Sep 2026 | typical late Nov-1 Dec (2026 cycle: 2025-12-01) | Mostly no (junior-oriented; math) | [3rd-party] math.mit.edu |
| NVIDIA Ignite / early talent | Summer 2027 | unverified | unverified | Unclear (targets freshmen/sophomores) | [3rd-party] |
| Company summer internships (semis, Bay Area) | Summer 2027 | Aug-Oct 2026 (typical) | rolling until filled, many fill by Dec-Feb | Mostly no (enrolled) | unverified |
| Company Spring 2027 part-time / remote | Spring 2027 | now | rolling | Case by case | unverified |

Calendar actions: the registry (T1) should store `typical_open`, `typical_close`, `verified_for_2027` per program and show "check again on <date>". Nothing should present a typical date as a real deadline.

## 4. Source table

Columns condensed. Cost is $0 and card is none for every row unless stated. "Stable IDs" = what the identity model can key on. Eligibility (E): HS = HS senior, IF = incoming freshman, FY = first-year.

| # | Source | Official URL | Category | E | 2027 season | Access / auth | Stable source / opportunity ID | Description / deadline / start / min age / education / citizenship text | Pagination / rate / closure | Terms / robots | Dedupe | Complexity | Value |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | SmartRecruiters Posting API | developers.smartrecruiters.com (posting-api) | ATS API | FY (varies) | both | JSON GET `api.smartrecruiters.com/v1/companies/{id}/postings`; **public data, no authentication by design** [official: the authentication guide names the Posting API]; only the INTERNAL destination needs a scope | company identifier / posting `id`+`uuid` | list has no description; detail GET (`/postings/{id}`) has `jobAd.sections`; no deadline field; `releasedDate`; `typeOfEmployment`, `experienceLevel`, `location` | `limit` (max 100) / `offset`, `totalFound`; rate limit unpublished; closed = absent from list | Documented public-data API; PUBLIC postings only | `smartrecruiters:{company}:{id}`; the feed names ~40 (`smartrecruiters:<Company>:<id>` + a `jobs.smartrecruiters.com` link) | MEDIUM | MEDIUM |
| 2 | USAJOBS Search API | developer.usajobs.gov | Government API | FY (student path) | both | JSON GET `data.usajobs.gov/api/search`; headers Host, User-Agent=requester email, Authorization-Key; free key via request form [official] | `MatchedObjectId` (control number) / `PositionID` | `QualificationSummary`, `MajorDuties`, `Requirements`, `Education`, `ApplicationCloseDate`, `PositionStartDate`, `HiringPath`; citizenship text in `WhoMayApply`/requirements | `Page`, `ResultsPerPage` max 500, max 10,000 rows/query [official rate-limit guide]; closure by `ApplicationCloseDate` and absence | Terms page: authorized-use, monitored; no commercial/redistribution wording seen; **review in full before ADR** | Unique to USAJOBS; Pathways postings do not exist elsewhere | MEDIUM | MEDIUM |
| 3 | Curated program registry (repo data) | n/a (each program's own page) | Manual/curated | HS, IF | both | none (data file) | `curated:{slug}:{cycle}` | whatever the owner transcribes with source URL | n/a; closure by `verified_until` date | owner-transcribed facts + link out; no copying of page prose | n/a | LOW | HIGH |
| 4 | NSF REU Directory | nsf.gov/funding/initiatives/reu/search | Federal directory | not eligible | Summer | HTML search; no export stated [official] | none | per-site pages | n/a | Government site; per-site terms | link-out only | n/a | MEDIUM (awareness) |
| 5 | NSF ETAP | etap.nsf.gov | Federal application platform | not eligible (REU) | Summer | `robots.txt` = `User-agent: *` `Disallow: /` [official fetch]; no public API found | none | none | none | **crawling disallowed** | n/a | n/a | n/a |
| 6 | NASA OSTEM / STEM Gateway | nasa.gov/learning-resources/internships ; stemgateway.nasa.gov | Federal | unclear | Spring (closed), Summer, Fall | login portal; no feed found (page did not render: **unverified**) | none | deadlines on nasa.gov page [official] | n/a | n/a | link-out | n/a | MEDIUM (manual calendar) |
| 7 | DOE SULI / CCI | science.osti.gov/wdts ; energy.gov | Federal | not eligible | Spring (closes 09-30), Summer | portal (account); no feed found | none | dates in DOE articles [official] | n/a | n/a | link-out | n/a | LOW for this student |
| 8 | Greenhouse / Lever / Ashby (existing) | per ADR-013 | ATS API | FY | both | already built | `provider:board:posting` | full text | already handled | per ADR-005 review | already | already built | HIGH |
| 9 | Recruitee careers API | docs.recruitee.com (careers-site-api) | ATS API | FY | both | `{company}.recruitee.com/api/offers/` pattern is [3rd-party]; doc page did not state auth | slug / offer id | description in offer JSON [3rd-party] | unverified | unverified | `recruitee:{slug}:{id}` | MEDIUM | LOW-MED |
| 10 | Breezy public JSON | breezy.hr | ATS | FY | both | `{company}.breezy.hr/json` [3rd-party only] | slug / `id` | unverified | unverified | unofficial | `breezy:...` | MEDIUM | LOW |
| 11 | Personio XML feed | support.personio.de (XML job integration) | ATS | FY | both | `{account}.jobs.personio.com/xml`, no credentials, customer must enable [official support page via search] | account / `id` | XML description | unverified | documented as the customer's own integration feed | `personio:...` | MEDIUM | LOW (EU-centric) |
| 12 | Workable | workable.readme.io | ATS | - | - | `/jobs` needs Bearer token with `r_jobs` [official] | - | - | - | - | - | - | rejected |
| 13 | Teamtailor | - | ATS | - | - | API token required [3rd-party] | - | - | - | - | - | - | rejected |
| 14 | BambooHR | - | ATS | - | - | `/careers/list` is the careers page's own JSON [3rd-party scrapers]; no documented public API | - | - | - | - | - | - | Tier 3 |
| 15 | iCIMS | developer.icims.com | ATS | - | - | Partner-gated API; sites' `/api/jobs` are internal search endpoints [3rd-party] | - | - | - | scraping an internal endpoint is outside ADR-005 | - | - | rejected |
| 16 | Workday | per tenant | ATS | - | - | no public API; CxS JSON is the career-site's internal endpoint | - | - | - | **hard constraint: no Workday scraping** | - | - | rejected |
| 17 | Eightfold, Phenom, SuccessFactors, Taleo, Jobvite, Rippling, JazzHR | - | ATS | - | - | gated/customer-scoped or internal endpoints [3rd-party] | - | - | - | - | - | - | rejected |
| 18 | National lab career portals | jobs.lbl.gov, llnl.gov/careers, careers.slac.stanford.edu, anl.gov, ornl.gov, nrel.gov, sandia.gov | Labs | unclear | both | HTML/Workday/other; Argonne uses Workday Recruiting [official anl.gov]; others not confirmed | - | - | - | - | link-out | - | LOW (link-out) |
| 19 | Semiconductor company career sites | see §10 | Company | IF rarely | Summer | mostly Workday-family | via feed only | - | - | Workday = excluded | feed IDs | - | LOW |
| 20 | Volunteer aggregators | (separate agent covers) | Aggregator | - | - | not evaluated | - | - | - | - | - | - | - |

## 5. Tier 1 (build next)

### 5.1 Curated HS / early-college program registry (value HIGH, complexity LOW)

- **What:** a committed JSON/YAML file of public program facts, imported through the existing curated-opportunity path (ADR-008 section 8 protects curated records from sync rewrites). No network call, no host allowlist change.
- **Why Tier 1:** the highest-value programs for this user (SIMR, UCSC SIP, LBNL Experiences in Research, NLR-SLAC Pathway, MIT RSI/PRIMES, REU sites that accept rising freshmen, NASA/DOE calendars) have no feed, some forbid crawling (ETAP), and most need human eligibility judgment. The registry makes the calendar visible and lets ADR-012 requirement suggestions apply.
- **Content rule:** facts only (name, org, URL, typical window, eligibility sentence paraphrased with a source link). No copied page prose, no personal data.
- **Risk:** stale dates. Mitigation: `verified_for_cycle` and `verify_by` fields; UI shows "typical, not confirmed".

### 5.2 SmartRecruiters Posting API (value MEDIUM, complexity MEDIUM)

- Public GET list per company identifier, JSON, paginated by `limit`/`offset` with `totalFound` [observed 2026-10-04 on the `smartrecruiters` company; fields: `id`, `name`, `uuid`, `refNumber`, `company`, `releasedDate`, `location` incl. `city/region/country/remote/hybrid/fullLocation`, `typeOfEmployment`, `experienceLevel`, `department`, `function`, `ref`, `language`].
- **Corrected classification: Tier 1, documented public-data access, no customer API key for PUBLIC postings.** SmartRecruiters' authentication guide states: "Some APIs provide access to public data and don't require authentication by design", naming the **Posting API** [official: developers.smartrecruiters.com/docs/authentication]. `GET /v1/companies/{companyIdentifier}/postings` lists a company's active public postings; the `internal_postings_read` scope is required only for the INTERNAL destination [official: reference page]. (An earlier draft of this note read the Posting API page's key/OAuth wording as covering public postings; that wording is about authenticated/internal access.)
- PUBLIC posting data only: never the INTERNAL or INTERNAL_OR_PUBLIC destinations, candidate APIs, application APIs, or job administration APIs. GET only.
- Verified on the live endpoint (2026-10-04): company identifiers are case-insensitive; a nonexistent company answers 200 with `totalFound: 0`; detail responses carry `jobAd.sections.{companyDescription,jobDescription,qualifications,additionalInformation}.{title,text}` (HTML), `postingUrl`, `applyUrl`, `company.identifier`.
- Description text requires a per-posting detail GET (N+1). The adapter must cap detail fetches per sync (see task card).

### 5.3 USAJOBS Search API (value MEDIUM, complexity MEDIUM, owner-gated)

- Free key requested by the owner via the developer portal [official: developer.usajobs.gov/guides/authentication: "Anyone can request access"; cost not stated, so **treat as free but unverified**]. Required headers: `Host: data.usajobs.gov`, `User-Agent: <email used for the key>`, `Authorization-Key`. The User-Agent must therefore contain the owner's email, which conflicts with the repo's public User-Agent; the key and email must be env-only secrets and never logged or committed.
- `HiringPath=student` identifies student-hiring-authority postings [official: get-api-search page]. Whether HS students qualify for a given Pathways posting is **unverified**; NASA's own page says Pathways needs 15 semester hours [official], so most NASA Pathways postings will be ineligible. Eligibility engine should surface this rather than hide it.
- Fields: `PositionID`, `MatchedObjectId`, `ApplicationCloseDate`, `PositionStartDate`, `QualificationSummary`, `UserArea.Details.{MajorDuties,Requirements,Education,HiringPath}` [official]. Pagination: 500/page, 10,000 rows/query max [official rate-limit guide]. Rate limits beyond that unverified.
- Gate: ADR-014 must approve a secret-bearing source (new env var) and the USAJOBS terms must be re-read in full first.

### 5.4 Existing ATS expansion (no new adapter)

Keep ADR-013 discovery as the way to add Greenhouse/Lever/Ashby boards, and add a short, owner-reviewed docs list of candidate boards. No code in M8 beyond optional seed UI text. (Which semiconductor/hardware companies actually use these three ATSs is **unverified**; verify each by opening its careers page once.)

## 6. Tier 2 (after Tier 1)

- **Recruitee** careers API: low-traffic startups use it; doc page says the API exists for "viewing company's jobs" but does not state auth [official, incomplete]. Do a manual check of a sample board's response and terms before committing. Identity `recruitee:{slug}:{id}`.
- **Personio XML feed**: officially documented as a no-credentials XML feed the customer enables [official support article]. EU-heavy; Bay Area value is low. Needs an XML parser with entity-expansion protection (defusedxml-style) so the adapter must not use a naive XML parser.
- **Breezy `/json`**: only vendor-adjacent evidence. Tier 2 only if an official doc is found.
- **Seeded "Spring 2027 part-time" saved-search** over existing sources (filter by term "spring", "part-time", "remote") as a UI feature, not a source.
- **Lever/Greenhouse EU hosts** already handled.

## 7. Tier 3 (monitor / manual)

- **NASA OSTEM / STEM Gateway**: manual registry entries with the official deadline table. Re-check Summer 2027 window in Dec 2026 (sources disagree: nasa.gov says 2027-03-01; one third-party says 2027-02-26).
- **DOE SULI/CCI** (portal science.osti.gov/wdts): manual entries; not owner-eligible unless enrolled.
- **NSF REU Directory** (nsf.gov REU search, and etap.nsf.gov): manual links only. ETAP forbids all crawling via robots.txt [official fetch]. Some REUs accept incoming freshmen at the PI's discretion: **unverified**; owner should ask.
- **National lab portals** (LBNL, LLNL, SLAC, ANL, ORNL, NREL, Sandia): link-out. ATS confirmed only for Argonne (Workday Recruiting, internal) [official anl.gov]; others unverified.
- **BambooHR**, **JazzHR** boards: HTML/internal JSON; not documented as public APIs.
- **University summer research programs** (Stanford SIMR, UCSC SIP, MIT RSI/PRIMES, Garcia and others): registry entries only; most exclude the owner's cohort. Berkeley/UC programs: unverified.
- **Semiconductor intern programs** (NVIDIA, AMD, Intel, Apple, Qualcomm, TI, ADI, Applied Materials, Lam, KLA, Broadcom, Microchip): see §10; track via the discovery feed where it names Greenhouse/Lever/Ashby, otherwise manual.
- **Bay Area local STEM orgs / nonprofits**: add case by case to the registry after finding a posting URL; no crawler.

## 8. Reject

| Candidate | Reason |
|---|---|
| Workday (any tenant) | Hard constraint: no Workday scraping; no public API; many feed links are Workday and stay link-out only |
| iCIMS, Eightfold, Phenom, SuccessFactors, Taleo, Jobvite | Partner/customer-gated APIs; public data only via internal endpoints that power career-site JavaScript, which is outside ADR-005's "structured, permitted" bar |
| Workable | Official `/jobs` requires Bearer token with `r_jobs` [official]; no documented public endpoint |
| Teamtailor | API token required [3rd-party]; $0 posture means no per-customer tokens |
| Rippling | Partner-gated API; no public listing endpoint [3rd-party] |
| NSF ETAP crawling | `robots.txt` disallows everything [official] |
| STEM Gateway scraping | Account-gated portal, no feed found; scraping prohibited by our constraints |
| Third-party scraper services (Apify actors, jobspipe, etc.) | Paid or key-gated; some resell scraped data; license unclear |
| Any listing repo whose data license is unclear (see `SuryaHarikrishnan/2027-internship-tracker` in sources.md) | Already excluded in ADR-005 |
| Browser automation of any career site | Hard constraint |

## 9. ATS family survey

| ATS | Public unauthenticated posting endpoint? | Evidence | Verdict |
|---|---|---|---|
| Greenhouse | Yes, `boards-api.greenhouse.io/v1/boards/{board}/jobs` | existing adapter, sources.md | Supported |
| Lever | Yes, `api.lever.co/v0/postings/{site}` (+ EU) | existing adapter; [3rd-party] public, unauthenticated | Supported |
| Ashby | Yes, `api.ashbyhq.com/posting-api/job-board/{board}` | existing adapter | Supported |
| SmartRecruiters | Yes: the Posting API is documented as public data without authentication (PUBLIC destination) | [official] authentication guide + reference | Tier 1 (ADR-014) |
| Recruitee | Careers Site API exists; auth statement unclear | [official, incomplete] | Tier 2 |
| Personio | XML feed, no credentials, customer-enabled | [official support] | Tier 2 (EU) |
| Breezy | `{co}.breezy.hr/json` | [3rd-party] only | Tier 2/3 |
| BambooHR | `/careers/list` is page-internal JSON | [3rd-party] | Tier 3 |
| Workable | Token required for `/jobs` | [official] | Reject |
| Teamtailor | Token required | [3rd-party] | Reject |
| JazzHR | No cross-customer public endpoint; account-scoped XML/REST | [3rd-party] | Reject |
| Jobvite | Customer must enable job feed; no universal endpoint | [3rd-party] | Reject |
| iCIMS | Partner program; internal `/api/jobs` on some sites | [3rd-party] | Reject |
| Rippling | Partner-gated | [3rd-party] | Reject |
| Workday | No public API | hard constraint | Reject |
| Eightfold, Phenom | Not confirmed; internal career-site APIs | unverified | Reject |
| SuccessFactors, Taleo | Customer-scoped APIs | [3rd-party] | Reject |
| Pinpoint | Docs URL returned 404; unverified | - | Unverified, skip |

### Likely ATS per semiconductor/lab target (all unverified unless stated)

| Company / lab | Likely careers platform | Evidence | Supported adapter? |
|---|---|---|---|
| NVIDIA | Workday (`nvidia.wd5.myworkdayjobs.com`) | [3rd-party] | No |
| Intel | Workday (`intel.wd1.myworkdayjobs.com`) | [3rd-party] | No |
| KLA | Workday (`kla.wd1.myworkdayjobs.com`) | [3rd-party] | No |
| Analog Devices | Workday | [3rd-party] | No |
| Microchip | Workday | [3rd-party] | No |
| Applied Materials | own site `jobs.appliedmaterials.com` (backend unverified) | URL pattern only | No |
| AMD, Qualcomm, TI, Broadcom, Lam, Apple | not confirmed | - | Unknown |
| Argonne | Workday Recruiting | [official] anl.gov | No |
| LBNL, LLNL, SLAC, ORNL, NREL, Sandia | not confirmed | - | Unknown |

Conclusion: the semiconductor tier is overwhelmingly Workday-family, so direct ingestion is out of scope; the owner reaches those roles through the discovery feed (link-out) and the registry.

## 10. M8 backlog task cards

### M8-T1: Curated program registry import

- **Adapter/source type:** `curated_registry` (new `ingestion_source_kind` value is NOT needed; reuse manual-curation path). Open question: whether to store as manual `Opportunity` rows via a CLI import or as a new built-in source kind; recommend a CLI/management command that creates curated opportunities, keeping the shared pipeline as the writer.
- **Network host allowlist:** none (no network).
- **Safe source configuration:** a repo file `data/program_registry.yaml` (public facts only). Owner edits via PR. Validation: schema with required `slug`, `name`, `organization`, `url` (https only, host not private), `typical_open`, `typical_close`, `verified_for_cycle`, `eligibility_note`, `source_url`. Reject unknown keys, URLs with credentials, any email/phone.
- **Identity model:** `curated:{slug}:{cycle}` (e.g. `curated:ucsc-sip:2027`).
- **Normalization mapping:** title=`name`; org=`organization`; location=`location`; description=owner-written one-paragraph summary (not copied prose); deadline=`verified_close` only if verified, else null with `typical_close` in a notes field; start date=`typical_start`; type=`research|internship|program`; application URL=`url`.
- **Closure behavior:** past `verified_close`, or `verify_by` elapsed, marks stale; never auto-deletes.
- **Requirement-text availability:** the `eligibility_note` paragraph feeds ADR-012 suggestions; mark source `curated_note`.
- **Tests:** schema validation rejects bad URLs/keys; idempotent re-import; curated rows not overwritten by sync; stale date handling; no PII in fixtures.
- **Complexity:** LOW.

### M8-T2: SmartRecruiters adapter

- **Adapter/source type:** new `smartrecruiters` kind, `source_type=ats` (authority rank 0 under ADR-013).
- **Network host allowlist:** `api.smartrecruiters.com` only (exact match; HTTPS, no userinfo, default port per `http.py`). Posting links go out to `jobs.smartrecruiters.com` (link only, not fetched, not allowlisted).
- **Safe source configuration:** owner enters a company identifier or a `jobs.smartrecruiters.com/{company}` URL. Validation: parse host exactly, take the first path segment, apply the shared slug pattern; refuse everything else. Default scope Internships only, like ADR-013. Identifiers are case-insensitive at the provider (verified 2026-10-04), so store them lowercased like the other providers.
- **Identity model:** `smartrecruiters:{company}:{posting-id}`; `uuid` kept in the raw payload. The feed already names these postings (`smartrecruiters:<Company>:<id>` with a matching `jobs.smartrecruiters.com/<Company>/<id>` link), so discovery can map them exactly.
- **Normalization mapping:** title=`name`; org=configured display name; location=`location.fullLocation` (+ `remote`/`hybrid` flags into remote mode); description=detail endpoint `jobAd.sections` concatenated as text (structure verified on a live response, 2026-10-04); deadline=none (no field observed); start date=none; type from `typeOfEmployment.label` and `experienceLevel.label` plus title keywords; posted date=`releasedDate`; application URL=posting `ref`/public posting URL.
- **Closure behavior:** list returns active postings; absence from a complete paginated walk means closed; a partial/failed walk must never close records (same rule as other adapters).
- **Requirement-text availability:** only with the detail GET. Cap detail fetches per sync (e.g. 100/run), prioritize new/changed `id`s, skip when the title filter already excludes.
- **Tests:** fixture of a synthetic list response and detail response; pagination across `totalFound`; slug/URL validation negatives (trailing newline, userinfo, port, lookalike host); closure on complete vs incomplete walk; detail failure degrades to no-description, not a failed sync.
- **Complexity:** MEDIUM.

### M8-T3: USAJOBS adapter (owner-gated)

- **Adapter/source type:** new `usajobs` kind, `source_type=government_api` (authority rank 2 unless ADR-014 ranks it 0; recommend 0 since it is the original posting).
- **Network host allowlist:** `data.usajobs.gov`.
- **Safe source configuration:** owner supplies no URL; they set `USAJOBS_API_KEY` and `USAJOBS_USER_AGENT_EMAIL` as server env secrets (never in the DB or client, never logged). The source row stores only search presets: `HiringPath`, keyword list, locations, `DatePosted`. Validation: closed enums, keyword length/count caps, location allowlist pattern. Source is disabled and shows "key missing" until both env vars exist.
- **Identity model:** `usajobs:{MatchedObjectId}` (control number); announcement number `PositionID` in raw payload.
- **Normalization mapping:** title=`PositionTitle`; org=`OrganizationName`; location=`PositionLocation`; description=`QualificationSummary` + `MajorDuties` + `Requirements` + `Education` (text only); deadline=`ApplicationCloseDate`; start date=`PositionStartDate`; type=internship/pathways from `HiringPath`; URL=`ApplyURI`/`PositionURI`.
- **Closure behavior:** past `ApplicationCloseDate` = closed; absence from a complete walk = closed.
- **Requirement-text availability:** strongest of all sources (explicit requirements and citizenship text). Citizenship phrases feed ADR-012 suggestions as "needs verification", never as hard eligibility.
- **Tests:** synthetic response fixtures; header construction without leaking the key in logs/errors/stored payloads (assert redaction); pagination to 10,000-row cap; missing-key state; preset validation.
- **Complexity:** MEDIUM. **Blocker:** owner must decide to request the free key and accept a secret in config; USAJOBS terms must be re-read in full.

### M8-T4: Season-calendar view and "typical vs verified" labels

- **Adapter/source type:** none (UI/read model over T1 data).
- **Network:** none. **Configuration:** none.
- **Mapping:** reads `typical_open/close`, `verified_for_cycle`.
- **Closure:** shows "verify by" countdown.
- **Tests:** a typical date is never rendered as a confirmed deadline; sorting by next window.
- **Complexity:** LOW. (Optional; can fold into T1.)

### M8-T5 (Tier 2, not scheduled): Recruitee / Personio feed adapters

Decision gate: first confirm each vendor's terms and a real sample response. Allowlist would be `{slug}.recruitee.com` (per-tenant subdomains, so exact-match allowlisting needs a regex rule: **requires an ADR decision on wildcard hosts**) and `{account}.jobs.personio.com`. Do not build until ADR-014 resolves wildcard-host policy.

## 11. ADR-014 recommended scope

**Title:** Additional structured sources and the curated program registry.

**Decides:**
1. SmartRecruiters is an `ats`-class source (authority rank 0) with host `api.smartrecruiters.com`, the documented public Posting API only (PUBLIC destination, no key); never INTERNAL destinations, candidate, application, or job administration APIs.
2. Government API class (USAJOBS): allowed to hold one owner-supplied free key as a server-side env secret; rules for redaction, disabled-until-configured state, and authority rank.
3. Curated program registry: committed public-facts data file, imported as curated opportunities, with `typical` vs `verified` date semantics and a stale-after rule.
4. Host-allowlist policy for per-tenant subdomains (needed only if Tier 2 proceeds): exact hosts only, or a documented suffix rule; default exact.
5. The N+1 detail-fetch budget rule (per-sync cap) for adapters whose list lacks descriptions.
6. Eligibility semantics for time-aware status: "enrolled at start" vs "enrolled at application" per ADR-005, and that adapters never convert citizenship/enrollment text into hard eligibility.

**Explicitly excludes:**
- Workday, iCIMS, Eightfold, Phenom, SuccessFactors, Taleo, Jobvite, Rippling, JazzHR, Teamtailor, Workable, BambooHR adapters.
- NSF ETAP, NASA STEM Gateway, DOE WDTS portal ingestion (accounts/robots/no feed).
- Any HTML scraping, headless browser, or CAPTCHA handling.
- Third-party scraping services or aggregators with unclear licenses.
- Changing ADR-013 authority ranks other than adding the new source types.
- Volunteer aggregators (separate research).
- Automated company-to-ATS discovery beyond the existing feed-derived discovery.

## 12. Open questions for the owner

1. Would you accept holding a free USAJOBS API key as a server secret (the User-Agent header must carry the email used for the key)? If no, drop T3.
2. Are you enrolled, or will you be, in any dual-enrollment/community-college course in Spring/Summer 2027? That changes DOE CCI and many "enrolled student" postings from ineligible to eligible.
3. For admitted-but-not-matriculated status, should the eligibility engine treat "incoming freshman" as enrolled at start date (ADR-005 says projected status)? NASA and company postings often say "currently enrolled".
4. Which 5 to 10 Bay Area hardware/AI/robotics startups do you want checked first for Greenhouse/Lever/Ashby/SmartRecruiters boards?
5. Is a hand-maintained registry file in the public repo acceptable (facts + links only), or should it live in the private DB only?
6. Should the registry include programs you probably cannot apply to (e.g. RSI juniors-only) as "future/sibling" reference, or hide them?
7. ~~Is it acceptable to ship SmartRecruiters based only on observed anonymous access?~~ Resolved: SmartRecruiters documents the Posting API as public data without authentication.
8. Do you want a reminder mechanism for "verify by" dates (a UI banner is zero cost; email is out of scope)?

## Appendix: key official URLs

- SmartRecruiters Posting API: https://developers.smartrecruiters.com/docs/authentication ; https://developers.smartrecruiters.com/docs/posting-api ; https://developers.smartrecruiters.com/reference/getpostings-1
- USAJOBS: https://developer.usajobs.gov/ ; /guides/authentication ; /guides/rate-limiting ; /guides/terms-of-use ; /api-reference/get-api-search
- NASA internships: https://www.nasa.gov/learning-resources/internships/
- DOE Spring 2027 SULI/CCI: https://www.energy.gov/science/articles/discover-science-applications-open-spring-2027-undergraduate-internships ; portal https://science.osti.gov/wdts
- NSF REU students: https://www.nsf.gov/funding/initiatives/reu/students ; directory https://www.nsf.gov/funding/initiatives/reu/search ; ETAP https://etap.nsf.gov/ (robots: Disallow /)
- Workable API: https://workable.readme.io/reference/jobs
- Recruitee Careers Site API: https://docs.recruitee.com/reference/intro-to-careers-site-api
- Personio XML job integration: https://support.personio.de/hc/en-us/articles/29375445597725
- Argonne Workday Recruiting: https://www.anl.gov/hr/internal-applicants
