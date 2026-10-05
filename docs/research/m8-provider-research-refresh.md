# M8 provider research refresh

Research only. Nothing here is implemented; no endpoint other than public documentation pages and the public discovery feed JSON was requested. Date: 2026-10-04. Claims are labelled **[official]** (vendor docs read for this document), **[3rd-party]** (secondary source), **[unverified]** (not confirmed).

## a) Unsupported providers in the discovery feed

Feed fetched once on 2026-10-04 (`generated_at` 2026-10-05T01:33:40Z, `count` 1,105). Production context: 1,313 open opportunities, 20 direct ATS boards (13 Greenhouse, 2 Lever, 5 Ashby), description coverage 22.4% (294/1,313).

| ID prefix (before first `:`) | Items | % | Apply-link host family | Items | Supported by direct adapter? |
|---|---:|---:|---|---:|---|
| `workday` | 593 | 53.7% | `*.myworkdayjobs.com` / workday | 593 | No (ADR-014 section 10) |
| `greenhouse` | 207 | 18.7% | greenhouse hosts | 170 | Yes (37 more are Greenhouse-id items with a company-site apply link) |
| `oracle` | 147 | 13.3% | `*.oraclecloud.com` | 147 | No |
| `ashby` | 58 | 5.2% | ashbyhq | 58 | Yes |
| `smartrecruiters` | 40 | 3.6% | smartrecruiters | 40 | Yes (M8) |
| `lever` | 28 | 2.5% | lever | 28 | Yes |
| `rippling` | 11 | 1.0% | rippling | 11 | No |
| `amazon` | 9 | 0.8% | other (`www.amazon.jobs`) | 9 | No |
| `workable` | 8 | 0.7% | workable | 8 | No |
| `breezy` | 4 | 0.4% | other (`*.breezy.hr`) | 4 | No |

Other apply hosts (50 items, all "other"): the 37 Greenhouse-id items on company sites (e.g. akunacapital 6, careers.withwaymo 5, coinbase 5, careerpuck 4, pinterestcareers 3, hudsonrivertrading 3, epicgames 3), plus amazon.jobs 9 and breezy 4.

Notes:
- Workday is the dominant unsupported source: 593 items across 172 distinct tenants (largest: `bah` 67, `globalhr` 28, `caci` 24, `gdit` 20, `leidos` 17, `gilead` 16).
- Oracle: 147 items over 24 hosts (top: `egug.fa.us2` 33, `fa-evmr-saasfaprod1.fa.ocs` 21, `hdjq.fa.us2` 18, `hdhl.fa.us6` 17). Feed ID shape `oracle:<host>:<numeric requisition id>`; apply link `https://<host>/hcmUI/CandidateExperience/en/sites/CX_1/job/<id>`.
- Unsupported-provider total (workday + oracle + rippling + amazon + workable + breezy) = 772 of 1,105 (69.9%) of the feed. These stay link-out rows with feed-only data (no description).

## b) Oracle Cloud HCM (Oracle Recruiting Cloud)

| Question | Finding | Label |
|---|---|---|
| Is there a documented REST resource for requisitions? | Yes: `recruitingCEJobRequisitions`, `GET /hcmRestApi/resources/11.13.18.05/recruitingCEJobRequisitions[/{SearchId}]` plus two POST actions (location coordinates, details for map). | [official] docs.oracle.com `api-recruiting-ce-job-requisitions.html` |
| Is it intended for third parties? | The page states: "the service endpoints in this resource category are only for Oracle internal use." | [official] |
| Same for the details resource? | `recruitingCEJobRequisitionDetailsPreviews` (path param `RequisitionId`; LOB attributes `ExternalDescription`, `ExternalQualifications`, `ExternalResponsibilities`, `ShortDescription`) is described as for Oracle internal use only. The exact wording was obtained through a summarizing fetch, so re-read the page before relying on it. | [official], partly [unverified] wording |
| Is anonymous access documented? | No. The REST Quick Start documents only authenticated access: Basic over SSL, SAML 2.0 bearer, JWT, OAuth 2.0 (OWSM policy `oracle/multi_token_over_ssl_rest_service_policy`), with role-based authorization. No anonymous mode is documented. | [official] (absence of documentation; not proof the endpoint rejects anonymous calls) |
| Do public candidate sites call these endpoints anonymously? | Public career sites (the `hcmUI/CandidateExperience` front end) work without login, and third parties report the front end uses internal `hcmRestApi` calls. Not tested here (not allowed). | [3rd-party] (jobspipe.dev; search summary says the REST API is tenant-scoped and credentialed), [unverified] |
| Stable job ID? | Numeric requisition id appears in the public job URL (`.../job/40677`); the discovery feed already derives a stable ID from host + id. Whether it is stable across re-posting is not documented. | [unverified] (observed in feed) |
| Description endpoint? | Documented only in the internal-use resources above. A public description would need the HTML job page. | [official] / [unverified] |
| Host patterns | `<tenant>.fa.<region>.oraclecloud.com` (e.g. `egug.fa.us2`, `hdhl.fa.us6`), `fa-<code>-saasfaprod1.fa.ocs.oraclecloud.com`, and vanity `jpmc.fa.oraclecloud.com`; site code `CX_1` is one of several possible site numbers per tenant. | Observed in feed (24 hosts) |
| Terms of use for scraping the candidate sites | Not read for this document (Oracle Cloud services agreement is per-customer; each employer owns its site). | [unverified] |

**Verdict: link-out only.** The only documented requisition API is labelled internal-use-only and documents only authenticated access; using the same calls the candidate front end makes would be using an undocumented internal endpoint, which ADR-005 (documented, permitted access only) and ADR-014 section 10 ("Oracle Cloud HCM internal endpoints" excluded) forbid. No code, no adapter. Revisit only if Oracle publishes an anonymous external-candidate API, or a specific employer offers a documented feed.

## c) Other providers

| Provider | Finding | Verdict |
|---|---|---|
| Rippling (11) | Rippling documents a per-company Job Board API for rendering one company's jobs on its own site; the platform API is partner-gated OAuth. Rippling guidance reportedly forbids using a key on behalf of another organization. Could not confirm doc text directly (fetch returned nothing). | [3rd-party] / [unverified]. Link-out only. |
| Workable (8) | Official API is account-scoped: bearer token generated by an Admin of that Workable account, scope `r_jobs`, endpoint `https://<subdomain>.workable.com/spi/v3/jobs`. No anonymous documented API. Official developer page 404'd on direct fetch; facts from help-centre/readme search summaries. | [3rd-party summaries of official docs]. Link-out only (needs each employer's token). |
| Workday (593) | Biggest gap, but public job pages sit behind an undocumented `wday/cxs` JSON used by the front end; ADR-014 excludes it. | Link-out only; revisit needs a fresh ADR. |
| Amazon (9), Breezy (4) | Single-company site / small ATS; not evaluated for documented public APIs. | [unverified]. Link-out; low volume. |

## d) Future card: USAJOBS Search API (M8.x, owner-gated)

**Not implemented in M8. It needs an owner-provided API key and a separate ADR decision before any code.** Facts checked against developer.usajobs.gov on 2026-10-04.

| Topic | Detail |
|---|---|
| Endpoint | `GET https://data.usajobs.gov/api/search?...` [official] |
| Required headers | `Host: data.usajobs.gov`; `User-Agent: <the email address used to request the key>`; `Authorization-Key: <API key>` [official, authentication guide]. Code-list APIs need no auth. |
| Key | Obtained by application at developer.usajobs.gov/apirequest with the owner's email. The owner's email is therefore part of every request (User-Agent) and must come from a server-only env var, not be committed (public repo). |
| Pagination | `Page`, `ResultsPerPage` (max 500); max 10,000 rows per query; `DatePosted` 0-60 days [official, API reference + rate-limiting guide]. Default shows only "Public" postings (`WhoMayApply`: All / Public / Status); a separate request is needed for "Status". |
| Filters | `HiringPath` (20+ values incl. `student`, `public`, `vet`, `fed-competitive`), `Keyword`, `PositionTitle`, `Organization`, `JobCategoryCode`, `LocationName`, `RemoteIndicator`, `SecurityClearanceRequired`, `SortField`/`SortDirection`. `Fields=Min|Full` controls detail. |
| Response fields | `MatchedObjectId` (control number), `PositionURI`, `PositionTitle`, `JobSummary`, `QualificationSummary`, `UserArea.Details` (duties, education, requirements), `PublicationStartDate`, `ApplicationCloseDate`, `PositionRemuneration`, `SearchResultCount(All)`. |
| Terms | Terms-of-use page fetched, but content is generic government-system language ("authorized users only", monitoring, no misuse). No explicit rate limit, attribution or caching rule found. Re-read the live Terms and the rate-limit guide at ADR time and record dates. [official, incomplete] |

Design proposal (for the future ADR; not a decision):

| Area | Proposal |
|---|---|
| Source kind | New `usajobs` kind, one configurable source row ("preset"), default off. |
| Secrets | `USAJOBS_API_KEY` and `USAJOBS_USER_EMAIL` as server-only env vars (backend only, never `NEXT_PUBLIC_*`). Never logged, never stored in DB/raw payloads, never in error messages or URLs, never committed (`.env.example` placeholders only). Redaction tests: HTTP error/exception text, run summaries and stored raw items must not contain either value; request headers excluded from any logged object. Missing key = source reports a clear "not configured" state, never a crash. |
| Presets (source config) | `student-internships`: `HiringPath=student`, `DatePosted=60`, `ResultsPerPage=500`, `Fields=Full`; optional keyword preset (e.g. Pathways / internship). Bounded page count (10,000-row cap) and a short timeout. |
| Identity | `usajobs:<MatchedObjectId>`; apply URL = `PositionURI`. |
| Authority (proposal) | Higher than the discovery feed (official agency source for dates and description); canonical title, deadline (`ApplicationCloseDate`), description, location. Needs an explicit decision in ADR-013's authority ladder. |
| Closure | Missing from a complete, error-free run for the preset's full result set, or `ApplicationCloseDate` passed; an incomplete run (cap hit, page error) closes nothing. |
| Requirement text | `QualificationSummary` + `UserArea.Details` education/requirements go through the unchanged extractor; candidates stay pending. Note federal "U.S. citizen" language is common and many roles are not for high-school students (Pathways has age/enrollment rules): expect citizenship/age proposals needing owner review. |
| Tests | Fixture-based (synthetic JSON): pagination, 500/page and 10,000-row cap, header construction without leaking the key, redaction in errors and logs, missing-key behaviour, `Status` vs `Public` default, closure safety on partial run. |
| Re-read before build | Authentication guide, Terms of Use, rate-limiting guide, API reference (all under developer.usajobs.gov), and the key-request terms. |
