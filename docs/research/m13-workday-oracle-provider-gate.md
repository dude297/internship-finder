# M13 Workday, Oracle, and provider-family source gate

> **Research only (non-normative).** Date: 2026-10-06. Last verified: 2026-10-06.
> Used by / superseded by: nothing yet; extends [m8-provider-research-refresh.md](m8-provider-research-refresh.md), [direct-company-source-matrix.md](direct-company-source-matrix.md), and [direct-source-expansion-2026-10-06.md](direct-source-expansion-2026-10-06.md). No ADR cites it. No code was written.

Question: does any of Workday, Oracle Recruiting Cloud, the other ATS families, or the mega-cap first-party career sites offer a source that passes the permanent source rules ($0, no keys, official/documented before undocumented, no bot-control bypass, no internal APIs, no other tracker's data)? All access dates below are 2026-10-06.

Method and limits: vendor docs read through WebFetch/WebSearch; robots.txt, sitemaps, and a few public job pages fetched once or twice each with a research User-Agent, no POST, no `wday/cxs` call, no login, no WAF bypass. Oracle's `docs.oracle.com` REST pages are JavaScript-rendered and could not be read by the fetcher; Oracle claims therefore rest on the prior note's reading plus search snippets quoting the page, labelled below. Vendor pages that returned nothing are labelled **[unverified]**. Third-party pages (Apify actors, jobspipe.dev, getknit.dev) are used only to point at what to verify, never as evidence of permission.

## Gate used

GREEN needs all of: official/public; stable identity; no credentials; free; bounded; closure semantics possible; clearly intended public job access. YELLOW = public but missing at least one of those (usually undocumented, or no safe closure). RED = credentialed, internal-only, explicitly forbidden, or bot-blocked. Precedent for GREEN: Workable widget API and Pinpoint `postings.json` ([direct-company-source-matrix.md](direct-company-source-matrix.md)), both documented keyless public feeds.

## Result summary

| Family | Class | One-line reason |
|---|---|---|
| Workday (`*.myworkdayjobs.com`, `*.myworkdaysite.com`) | **YELLOW** (new evidence) | No developer API; but robots.txt advertises a per-site `siteMap.xml` and each job page carries schema.org `JobPosting` JSON-LD; sitemap is capped at the newest 100 URLs, so no closure by absence |
| Workday `wday/cxs` JSON | **RED** | Undocumented front-end endpoint; ADR-014 §10 excludes it; not requested |
| Oracle Recruiting Cloud | **RED** | Documented requisition REST is internal-use and authenticated; no robots/sitemap/feed on candidate-experience hosts; WAF on at least one host |
| Personio | **GREEN** (conditional) | Vendor-documented public XML feed, one request, full list, id + createdAt; EU-heavy |
| Teamtailor | **GREEN** (conditional) | Vendor-documented public RSS with `offset`/`per_page`, guid + pubDate; EU-heavy |
| Recruitee | RED | Careers API token mandatory from 2027-02-10; XML feed is "generated per job board" with no documented public URL |
| Breezy | YELLOW | `<co>.breezy.hr/json` keyless but not found in vendor docs |
| Rippling | YELLOW | Vendor-documented Job Board API for a company's own site (Recruiting Pro); primary page unreadable |
| BambooHR | RED | HRIS API needs customer key; careers list is widget/HTML only |
| JazzHR | RED | XML feed and API need the customer's key |
| Jobvite | RED | Feed is opt-in per customer; API credentialed |
| iCIMS | RED | Standard XML feed for job boards requires OAuth 2.0; portals are HTML |
| SuccessFactors | RED | OData needs permissions; XML feeds are customer-configured (open or authenticated); "sitemal.xml" is undocumented |
| Taleo | RED | RSS is an admin toggle, 10 jobs per feed |
| Avature | RED | Server-rendered search HTML only; no documented feed |
| Phenom | RED | Jobs API is OAuth 2.0 by request |
| Eightfold | YELLOW | robots.txt explicitly allows `/api/pcsx`, but the API is undocumented; terms unreviewed (unchanged) |

Mega-caps are in the last section. Nothing in this note is implemented; every YELLOW or GREEN below needs owner approval and a new ADR first.

## 1. Workday

### Findings

| Question | Finding | Label |
|---|---|---|
| Documented public job interface, supported feed, or public search API? | None found. Workday's developer surface covers customer-credentialed HR integrations. Search results describing a "public Workday jobs API" are third-party scraper listings built on the front end's own `/wday/cxs/` calls. | [official] (absence); [3rd-party] for the cxs claim: apify.com/johnvc/workday-careers-api, peerlist.io (accessed 2026-10-06) |
| `POST .../wday/cxs/<tenant>/<site>/jobs` | Public-but-undocumented. It is the careers page's own XHR. Not fetched, not documented by Workday, and ADR-014 §10 / ADR-013 §8 exclude Workday. | RED for this project |
| robots.txt on tenant hosts | Present and permissive for the site path; **advertises a sitemap**. Verified live on `nvidia.wd5`, `intel.wd1`, `bah.wd1`, `gilead.wd1`, `gdit.wd5`, `leidos.wd5`, `nxp.wd3`, `globalfoundries.wd1`, `sec.wd3`, and `snapchat` (myworkdaysite): all list `Sitemap: https://<host>/<site>/siteMap.xml` plus `Allow: /<site>/` and `Disallow: /refreshFacet/`. NVIDIA also disallows `/NVIDIAExternalCareerSiteResearch/` and `/talentcommunity/`; Gilead disallows one early-talent site. Two guessed hosts (`caci.wd1`, `globalhr.wd1`) returned no robots (wrong datacenter guess, not a finding). | observed |
| Sitemap contents | `<urlset>` of job URLs with an `xhtml:link hreflang="en-US"` alternate, no `lastmod`. **Exactly 100 URLs on all 8 sitemaps fetched** (NVIDIA, Intel, BAH, GDIT, Leidos, NXP, GlobalFoundries, Snap), however large the tenant. Sampled NVIDIA entries (positions 0, 50, 99) had `datePosted` 2026-10-06, 2026-10-05, 2026-10-04, so it is a newest-100 window. Intern-slug share inside the window: NVIDIA 13 of 100, Intel 16 of 100, Booz Allen 0 of 100. | observed |
| JSON-LD on job pages | Yes. A NVIDIA job page (200 `text/html`, 15 KB) contains one `application/ld+json` `JobPosting` with `title`, `description` (full), `identifier.value` (requisition id, e.g. `JR2025478`), `datePosted`, `employmentType`, `hiringOrganization`, `jobLocation`. One sampled posting had a real-looking `validThrough` (3 days out); others had none. | observed |
| Is JSON-LD intended? | Yes. Workday's admin guide says it ensures postings "are compliant with Google for Jobs search" and lists date posted, employment type, hiring organization, description, location, and title as the structured fields (doc.workday.com/admin-guide/.../guu1532468933210.html, accessed 2026-10-06). The page does not mention sitemaps. | [official] |
| Unknown job URL | `GET .../job/.../Nonexistent-Role_JR1000001` returns HTTP **200** with the app shell and **no** JSON-LD. So HTTP status is not a closure signal; JSON-LD absence might be. A genuinely closed posting was not tested (no known closed URL). | observed, [unverified] for closed jobs |
| Workday terms | Workday's Online Terms of Service forbid "data mining, robots or similar data gathering or extraction methods designed to scrape or extract data from our Sites", ignoring robots.txt, and developing applications that interact with "our Sites" without written consent (workday.com/en-us/legal/site-terms.html, accessed 2026-10-06). The fetched summary says the "Sites" definition covers workday.com, the Community, and Workday APIs, not customer career sites; this reading is **[unverified]** and needs a human read of the full definition. Customer career sites are owned by each employer. | [official], interpretation unverified |
| Bot controls | Responses came through Cloudflare (`cf-ray`, `__cf_bm` cookies). robots.txt and the sitemap were served to a plain research UA without challenge; heavier use was not tested. A third-party article claims Akamai blocking and a 10,000-result cap on the cxs search; not verified here. | observed / [3rd-party] |

### Classification: YELLOW

Why not GREEN: (1) no developer-facing interface; the sitemap and JSON-LD are search-engine plumbing, not a feed; (2) the sitemap is a newest-100 window, so **absence from it cannot close anything** and a large tenant's internships older than the window are invisible; (3) closure signals are unproven (`validThrough` is sporadic, a closed page's behaviour untested); (4) Workday's terms text is not clearly inapplicable; (5) per-job N+1 fetches.

Why it is still the best expansion path: Workday is 593 of 1,105 feed items across 172 tenants (53.7%, [m8-provider-research-refresh.md](m8-provider-research-refresh.md)), all link-out with no description today. A robots-advertised sitemap plus Workday-documented JSON-LD is "official static structured data" in the ADR hierarchy, and it is the only Workday surface that stays inside robots.txt and the permanent rules.

### Architecture card (YELLOW): `workday_sitemap` discovery-only adapter

| Aspect | Design |
|---|---|
| Kind and authority | New source kind (record `source_type` `career_page`, ADR-015 §8). Rank with `ats` in `_SOURCE_RANK` only after approval. Discovery and enrichment only; **never a closer**. |
| Config | Owner supplies a careers URL; only `{host, site}` is kept and the link is never requested as given. Host allowlist: `{tenant}.wd{N}.myworkdayjobs.com` and `wd{N}.myworkdaysite.com` (exact patterns, N = 1-12 digits, no trailing dot, HTTPS 443, no userinfo, public DNS, existing `app/ingestion/http.py` rules). Tenant `^[a-z0-9][a-z0-9-]{0,62}$`; site `^[A-Za-z0-9_-]{1,64}$` (case preserved, Workday sites are case-sensitive). For myworkdaysite: path `/recruiting/<tenant>/<site>/`. |
| Pre-flight | Fetch `https://<host>/robots.txt` each run; require the site path to be allowed and to list the sitemap; refuse otherwise (honours per-tenant disallows such as NVIDIA's `Research` site). |
| Requests | 1 sitemap (`https://<host>/<site>/siteMap.xml`) + detail fetches only for URLs whose title slug matches the internship filter (intern/co-op/student/etc.) and that are not already fresh. Cap 25 detail fetches per source per run (the ADR-014 §2 detail budget), concurrency 1, 1 request/second, hard timeout, honour 429/Retry-After by stopping the run. No POST, no `cxs`, no search UI. |
| Identity | `workday:<host>:<site>:<JR/R id from identifier.value>`; the sitemap slug suffix `_JR2025478` is the cross-check. Never re-key to the feed's id without the ADR-013 reconciliation rules. |
| Fields | `title`, `description` (sanitize HTML), `datePosted` (verified date, ADR-014 §6), `jobLocation` (locality, region, country), `employmentType`, `identifier.value`, `validThrough` when present. Apply URL = the canonical job page. |
| Closure | **None from absence** (window is 100 newest). Close only on (a) `validThrough` in the past, or (b) a re-fetch of a known URL that returns 200 with no `JobPosting` JSON-LD (needs the closed-page behaviour verified first, and a live-URL check which ADR-015 §3 currently rejects). Otherwise the record stays open and ages out under the existing staleness rules; the discovery feed remains the closer ([ADR-013 §5](../decisions/ADR-013-provider-enrichment-and-source-authority.md)). The `EMPTY_SNAPSHOT_GUARD` ([ADR-015 §10](../decisions/ADR-015-freshness-requirements-v2-and-independent-discovery.md)) applies to an empty sitemap. |
| Bounds | At most 50 enabled sources total (ADR-013 cap) shared with ATS sources; per run 1 + 25 requests per tenant. |
| Approval needed | (1) A new ADR that supersedes the Workday exclusion in ADR-014 §10 and ADR-013 §8 and rules on ADR-015 §3 if a live check is used; (2) a written owner review of the full Workday Online Terms "Sites" definition and, ideally, the tenant's own career-site terms; (3) a decision that sitemap/JSON-LD counts as "official static structured data" despite no developer documentation; (4) owner approval of each tenant (ADR-013 §3); (5) a kill-switch flag; (6) tests with synthetic sitemaps and JSON-LD only (public repo: no real employer text in fixtures). |
| Not recommended | Using the 593 feed-only Workday URLs as a crawl list, or following feed apply links to detail pages without the above approvals. |

## 2. Oracle Recruiting Cloud / Oracle Cloud HCM

| Question | Finding | Label |
|---|---|---|
| Documented requisition REST | `GET /hcmRestApi/resources/11.13.18.05/recruitingCEJobRequisitions[/{SearchId}]` in the Oracle Fusion Cloud HCM REST reference (docs.oracle.com/en/cloud/saas/human-resources/<release>/farws/api-recruiting-ce-job-requisitions.html). | [official] (prior note) |
| Internal-use? | Prior note: "the service endpoints in this resource category are only for Oracle internal use". This run could not re-read the page (JavaScript-rendered; fetches returned the landing page only). A search snippet quotes the same sentence for sibling `recruitingCE*` pages (`...-flexfields-facet`, `recruitingJobApplications`, `recruitingCEJobReferrals` in the 24b/24c/24d references), which corroborates the category-level wording but is **[unverified]** for the exact requisitions page in the current release. | [official] via snippets, [unverified] wording |
| Anonymous access documented? | No. The Oracle REST documentation covers authenticated access against a single customer's Fusion environment. | [official] (absence) |
| robots.txt on candidate-experience hosts | `egug.fa.us2`, `hdjq.fa.us2`, `hdhl.fa.us6`, `fa-evmr-saasfaprod1.fa.ocs`: HTTP 404 (no robots). `jpmc.fa.oraclecloud.com`: **blocked by a WAF ("W4S-402: Blocked by WAF4SaaS")** for a plain UA; not retried or worked around. | observed |
| Sitemap / JSON-LD / feed | No sitemap advertised; the candidate site is a JavaScript app. Oracle's Taleo has a Google structured data feature (support doc 2380216_1, login-gated); no equivalent public documentation found for Recruiting Cloud. Oracle Recruiting supports admin-configured RSS/XML output for syndication; a customer reported in 2025 that they could only provide an XML feed off-system (community.oracle.com thread 923749, login-gated). | [unverified] |
| TI (`careers.ti.com`) | Redirects to `edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/...`, confirming Oracle HCM. | observed |

### Classification: RED

The only documented requisition API is internal-use and credentialed; the candidate site's own XHRs are the same internal endpoints (ADR-014 §10); no robots-advertised static structured surface exists; and at least one host answers with a WAF block. Revisit only if Oracle publishes an anonymous external-candidate API or an employer publishes a documented feed. No architecture card.

## 3. Provider families

Closure column: what absence/removal semantics the surface offers.

| Family | Documented public unauthenticated listing surface? | Evidence | Closure semantics | Class |
|---|---|---|---|---|
| **Personio** | Yes. XML feed `https://<account>.jobs.personio.de/xml?language=<xx>` ("XML job integration automatically transfers jobs from Personio to your company website"; the developer hub shows the URL pattern and a PHP sample; support says published jobs appear at `<account>.jobs.personio.com/xml`) | developer.personio.de/docs/integration-of-open-positions; support.personio.de/hc/en-us/articles/207576365 (accessed 2026-10-06). Live GET of `personio.jobs.personio.de/xml?language=en`: 200 `text/xml`, `<position>` with `id`, `name`, `office`, `additionalOffices`, `department`, `recruitingCategory`, `employmentType`, `seniority`, `schedule`, `yearsOfExperience`, `occupation`, `createdAt`, `jobDescriptions`. A request for a non-existent account got **HTTP 429** (rate limiting after ~4 requests in one minute). No third-party restriction found; the FAQ page returned 403 to the fetcher. | Full open list in one response; position missing from a complete parse = closed | **GREEN (conditional)** |
| **Teamtailor** | Yes. RSS `https://<site>.teamtailor.com/jobs.rss` (add `.rss` to the jobs page), `offset` and `per_page` parameters, "by default ... the first 100 jobs", "all of the data is publicly available", consumed by LinkedIn Job Wrapping | support.teamtailor.com/en/articles/11171756-rss-feed-how-to-guide (accessed 2026-10-06). Live GET of `career.teamtailor.com/jobs.rss`: 200 `application/rss+xml`, 14 items with `title`, `description` (HTML), `link`, `guid` (UUID), `pubDate`, `remoteStatus`, `tt:locations` (name, city, country), `tt:department`, `tt:role`. `per_page=2&offset=1` honoured; `offset=9999` returned an empty channel (200). The JSON `api.teamtailor.com/v1/jobs` needs a customer token and is not used. The help page does not state refresh or removal behaviour. | Paginate until an empty page; absent from a complete pass = closed (removal behaviour unstated, test before relying) | **GREEN (conditional)** |
| Recruitee | Careers Site API `/offers` requires header `X-Careers-Sites-Token`; "Deadline for introducing the token to calls is 10 February 2027 ... `401 Unauthorized`"; "The XML offer feed and jobs widget are not covered by the Careers API token"; the feed is "generated per job board" with no public URL pattern documented | docs.recruitee.com/reference/authentication-1; docs.recruitee.com/docs/feed (accessed 2026-10-06) | Feed removes unpublished offers, but the feed is per partner job board | RED |
| Breezy | Public job board JSON `https://<co>.breezy.hr/json`, keyless; the vendor's API docs (developer.breezy.hr, base `https://api.breezy.hr/v3`) cover the authenticated API and I could not find the `/json` feed documented in them | developer.breezy.hr search results (accessed 2026-10-06); the `/json` surface comes from third-party pages only | Absence from a complete list | YELLOW |
| Rippling | Vendor "Job Board API" documented at developer.rippling.com/documentation/job-board-api, for a company rendering its own board, requires a Recruiting Pro subscription. The page is JavaScript-rendered and unreadable here, so auth, scope, and terms are **[unverified]**; prior notes saw keyless list 200 with no description/date | search snippet (accessed 2026-10-06) | Absence from list (N+1 detail fetch needed) | YELLOW |
| BambooHR | HRIS REST API with customer-issued key (`/v1/applicant_tracking/jobs` needs it); public careers list is the embeddable widget (`<co>.bamboohr.com/careers/list`), not a documented API | third-party summaries (jobspipe.dev, getknit.dev), accessed 2026-10-06; vendor docs not re-read | n/a | RED |
| JazzHR | XML feed and REST API per customer, API key from Settings > Integrations, subscription-tier gated (api.resumatorapi.com) | getknit.dev summary, accessed 2026-10-06 | n/a | RED |
| Jobvite | REST API credentialed per company; "job feed" must be enabled by the customer, off by default | third-party summaries (jobspipe.dev), accessed 2026-10-06 | n/a | RED |
| iCIMS | "Standard XML Feed for Job Boards" delivered 3x daily; consumers must support OAuth 2.0 | developer-community.icims.com/platform/services/standard-xml-feed-job-boards (accessed 2026-10-06) | n/a | RED |
| SuccessFactors | `JobRequisition` OData needs Recruiter Operator permissions; Career Site Builder XML feeds are per-customer and "open (publicly accessible) or authenticated"; an undocumented `sitemal.xml` exists per third parties | learning.sap.com course pages; SAP KBA 2361686 (accessed 2026-10-06) | n/a | RED |
| Taleo | Career Section RSS is an admin toggle, "up to 10 jobs plus a link" per feed | docs.oracle.com Taleo social-media guide (search result), accessed 2026-10-06 | n/a | RED |
| Avature | No documented feed; public HTML `/careers/SearchJobs` only | third-party (apify.com, fantastic.jobs), accessed 2026-10-06 | n/a | RED |
| Phenom | Developer jobs API is OAuth 2.0 via request to api-management@phenom.com | third-party summary, accessed 2026-10-06 | n/a | RED |
| Eightfold | `apply.careers.microsoft.com`, `explore.jobs.netflix.net`, `jobs.nvidia.com`, `careers.micron.com`, `careers.qualcomm.com` robots.txt all say `Disallow: /` then `Allow: /$`, `/careers`, `/api/apply`, `/api/pcsx`, `/careerhub/explore/jobs`, `/api/career_hub`; so `/api/pcsx` is robots-allowed, but no vendor documentation of it as a public API exists. Unchanged from prior YELLOW (Microsoft/Netflix sitemap + JSON-LD cards) | observed 2026-10-06 | Sitemap absence (prior card) | YELLOW |

### GREEN specification: Personio XML feed (rank 1 of the GREEN pair)

Conditional on: owner approval; a short read of Personio's legal terms (none found restricting use of the feed, but the FAQ page was not readable); a 429-safe client (one request per source per run).

| Item | Spec |
|---|---|
| URL template | `https://{slug}.jobs.personio.de/xml?language=en` (single GET, no pagination). `.jobs.personio.com` appears in support docs; start with `.de` only and verify `.com` before allowing it. |
| Host allowlist | `*.jobs.personio.de` (exact suffix match, single label for `{slug}`, HTTPS 443, no redirects off-host). |
| Identifier validation | `^[a-z0-9][a-z0-9-]{0,62}$` after lowercasing; the owner enters a slug or a `https://<slug>.jobs.personio.de` link and only the slug is kept. |
| Mapping | `position.id` -> id `personio:{slug}:{id}`; `name` -> title; `office` + `additionalOffices/office` -> locations; `department`, `recruitingCategory` -> tags; `employmentType` (`intern`/`trainee` values flag internships), `seniority`, `schedule`; `jobDescriptions/jobDescription` (`name`+`value` HTML) -> description (sanitize); `createdAt` -> posted date (verified); apply URL `https://{slug}.jobs.personio.de/job/{id}` (pattern assumed; confirm against the feed before building). |
| Closure | Position absent from a successfully parsed, non-empty response closes; empty response on a source with 10+ open records fails as `empty_snapshot` ([ADR-015 §10](../decisions/ADR-015-freshness-requirements-v2-and-independent-discovery.md)). 429/5xx/parse errors close nothing. |
| Bounds | 1 request per source per run, size cap per `http.py`, count cap (e.g. 2,000 positions), enabled-source cap shared with ATS sources. |
| Expected coverage | Personio is DACH/EU-centric; no Personio apply links appear in the feed ID breakdown, so expected gain for a US-based high-school profile is close to zero. |

### GREEN specification: Teamtailor RSS (rank 2 of the GREEN pair)

| Item | Spec |
|---|---|
| URL template | `https://{slug}.teamtailor.com/jobs.rss?per_page=100&offset={n}` |
| Host allowlist | `*.teamtailor.com` single label only. Customers on custom domains are not supported (a redirect off `teamtailor.com` is a failure; do not follow). |
| Identifier validation | `^[a-z0-9][a-z0-9-]{0,62}$` lowercased; slug extracted from a pasted `https://<slug>.teamtailor.com/jobs` link, nothing else requested. |
| Pagination | `offset += per_page` until an empty or short page; cap 10 pages (1,000 jobs). `per_page` above 100 not tested; keep 100. |
| Mapping | `guid` (UUID) -> id `teamtailor:{slug}:{guid}`; `title`; `description` (HTML, sanitize); `pubDate` -> posted date; `link` -> apply URL; `tt:locations/tt:location` (`tt:name`, `tt:city`, `tt:country`) -> location; `remoteStatus`; `tt:department`, `tt:role` -> tags. No employment-type field, so internship detection is title-based. |
| Closure | Absent from a complete, error-free paginated pass closes. Verify on a live account that a deleted job leaves the feed before enabling (the help page is silent on removal). Empty-snapshot guard as above. |
| Bounds | At most 10 requests per source per run; shared source cap. |
| Expected coverage | Nordic/EU-heavy; none in the current feed; low expected gain. |

Approval for both: (1) a new ADR adding the kinds, the host allowlist entries, and recording the terms read; (2) owner approval per source ([ADR-013 §3](../decisions/ADR-013-provider-enrichment-and-source-authority.md)); (3) synthetic fixtures only; (4) per-kind kill-switch flag; (5) `docs/sources.md` and ADR-015 §7-style provider table updated in the same change.

### YELLOW architecture cards (provider families)

| | Breezy | Rippling | Eightfold (Microsoft, Netflix, Micron, Qualcomm, NVIDIA front end) |
|---|---|---|---|
| Adapter shape | `GET https://{co}.breezy.hr/json` (one request, full list) | list `GET` then one detail `GET` per posting (N+1) | robots-listed sitemap -> job page JSON-LD (see [direct-company-source-matrix.md](direct-company-source-matrix.md) cards); never `/api/pcsx` |
| Host allowlist | `*.breezy.hr` single label | `ats.rippling.com` + the documented API host once confirmed | company career hosts, one by one |
| Identifier | `^[a-z0-9][a-z0-9-]{0,62}$` | company slug + posting UUID | slug filter on intern titles |
| Bounds | 1 request/run; count cap | list + <= 25 details/run | sitemap + <= 25 details/run |
| Closure | absent from a complete list | absent from a complete list (details only for new ids) | absence from sitemap (completeness unproven) |
| Approval needed | Vendor documentation of the `/json` feed found, or an owner decision to treat an unadvertised keyless public feed as acceptable (it is not a documented one); new ADR | Primary Job Board API page read (auth, terms, whether use on another company's board is allowed; Recruiting Pro gating may make the keyless list an unintended surface); new ADR | Written terms review per employer; completeness vs inventory; new ADR |
| Feed footprint | 4 items | 11 items | not Workday-sized; Microsoft 71 intern slugs of 2,307 |

## 4. Mega-cap and first-party sites

Platform column is as observed or carried forward; "official public structured source" means documented API, feed, or robots-advertised static structured data.

| Company | Provider / front end | Observed 2026-10-06 | Official public structured source? | Class |
|---|---|---|---|---|
| Amazon | In-house (`www.amazon.jobs`) | robots.txt disallows only `/internal` paths (and AhrefsBot); no documentation of `search.json`; third-party scrapers use the site's own search data | No documented API or feed; the search JSON is the site's own undocumented endpoint | YELLOW (feed link-out in practice) |
| Google | In-house | robots.txt disallows `/about/careers/applications/jobs/results` (and paged variants) | No | RED |
| Apple | In-house (`jobs.apple.com`) | `/robots.txt` 301s to a not-found page; search page is an app; prior note: sitemap with `lastmod`, no JSON-LD | Sitemap only, unadvertised | YELLOW |
| Microsoft | Eightfold PCSX (`apply.careers.microsoft.com`) | robots `Disallow: /` with allow-list incl. `/careers`, `/api/pcsx` | Prior: sitemap + JSON-LD, unadvertised in robots, completeness unverified; `/api/pcsx` robots-allowed but undocumented | YELLOW |
| Meta | In-house (`metacareers.com`) | robots.txt header forbids automated collection without written permission | No | RED |
| Netflix | Eightfold PCSX (`explore.jobs.netflix.net`) | same robots allow-list; prior: robots-listed sitemap + JSON-LD | Sitemap (prior card) | YELLOW |
| Tesla | In-house | `robots.txt` returned HTTP 403 "Access Denied" to a plain UA (bot-controlled; not retried) | No | RED |
| NVIDIA | **Both**: `jobs.nvidia.com` is Eightfold; the live Workday site `nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite` carries current 2027 internships with JobPosting JSON-LD | Workday robots advertises the sitemap (100-URL window; 13 of 100 intern slugs) | Workday sitemap + JSON-LD (same YELLOW as section 1); prior note listed Eightfold only | YELLOW (changed from CURATED_ONLY on new Workday evidence) |
| Intel | Workday (`intel.wd1.myworkdayjobs.com/External`) | robots advertises sitemap; 16 of 100 intern slugs | Workday sitemap + JSON-LD | YELLOW (changed from REJECT_AUTOMATION: that class applied to the cxs API, not to the sitemap) |
| AMD | iCIMS (`careers.amd.com`) | robots `Allow: /`, `crawl-delay: 5`, one http `Sitemap` line; prior: ids only | No documented feed (iCIMS XML feed is OAuth) | RED/feed link-out |
| Qualcomm | Eightfold | robots allow-list as above | Undocumented | YELLOW |
| Micron | Eightfold | robots allow-list; prior: sitemap ~500 URLs, no JSON-LD | Sitemap, no structured fields | YELLOW |
| Texas Instruments | Oracle HCM (`edbz.fa.us2.oraclecloud.com`) | redirect confirms | No (section 2) | RED |
| Analog Devices | Unverified (`careers.analog.com` timed out; `analog.com/en/careers.html` 307); prior note: Workday unverified | not resolved | No | unverified; treat as feed link-out |

## What changes in the repository's current guidance

- ADR-014 §10 excludes Workday as a platform. This note's only new evidence is that Workday **tenants themselves publish** a robots-advertised sitemap and Workday-documented JSON-LD; the exclusion was written about internal endpoints. Using either requires a new ADR that narrows or supersedes §10 (no change is made here).
- [direct-company-source-matrix.md](direct-company-source-matrix.md) classed Teamtailor and Personio YELLOW from snippets. Primary pages read today (Teamtailor help center, Personio developer hub and support pages) and live GETs support GREEN under the Workable/Pinpoint precedent. Recruitee changes from "token required from 2027-02-10" to RED with the added fact that its XML feed is per partner board.
- Rippling, Breezy remain YELLOW; BambooHR, JazzHR, Jobvite, iCIMS, SuccessFactors, Taleo, Avature, Phenom remain RED.

## Recommendation (ranking by expected internship coverage gain)

1. **Workday sitemap + JSON-LD (YELLOW, not buildable yet).** Largest addressable gap: 593 feed-only items, 172 tenants; includes NVIDIA and Intel. Partial by design (newest 100), discovery-only, no closure. Needs the ADR and terms read in section 1 first.
2. **Personio (GREEN, conditional).** Cleanest contract and an `employmentType` internship signal, but EU-centric; close to zero gain for the owner's US profile.
3. **Teamtailor (GREEN, conditional).** Same value profile, title-only internship detection.
4. Everything else: no action.

Nothing here is cleared to build. Both GREEN items are "GREEN pending governance": they pass the technical gate but add a new provider kind and host allowlist entries, which ADR-013 §3 and ADR-014 §1 treat as decisions for the owner.

## Evidence index (accessed 2026-10-06)

- Workday Online Terms: https://www.workday.com/en-us/legal/site-terms.html
- Workday admin guide, Google for Jobs: https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/job-postings/guu1532468933210.html
- Tenant robots/sitemaps: `https://nvidia.wd5.myworkdayjobs.com/robots.txt`, `.../NVIDIAExternalCareerSite/siteMap.xml`, `https://intel.wd1.myworkdayjobs.com/robots.txt`, `https://bah.wd1.myworkdayjobs.com/robots.txt`, `https://gilead.wd1.myworkdayjobs.com/robots.txt`
- Oracle REST reference: https://docs.oracle.com/en/cloud/saas/human-resources/24d/farws/api-recruiting-ce-job-requisitions.html (JS-rendered; not readable by the fetcher)
- Personio: https://developer.personio.de/docs/integration-of-open-positions, https://support.personio.de/hc/en-us/articles/207576365
- Teamtailor: https://support.teamtailor.com/en/articles/11171756-rss-feed-how-to-guide
- Recruitee: https://docs.recruitee.com/reference/authentication-1, https://docs.recruitee.com/docs/feed
- Rippling: https://developer.rippling.com/documentation/job-board-api (unreadable)
- Breezy: https://developer.breezy.hr/
- iCIMS: https://developer-community.icims.com/platform/services/standard-xml-feed-job-boards
- Robots: https://www.amazon.jobs/robots.txt, https://www.google.com/robots.txt, https://www.metacareers.com/robots.txt, https://apply.careers.microsoft.com/robots.txt, https://explore.jobs.netflix.net/robots.txt, https://careers.amd.com/robots.txt
