# Direct Company Source Matrix

> **Research only (non-normative).** Date: 2026-10-05. Last verified: 2026-10-05.
> Used by / superseded by: [ADR-015 §6-§8](../decisions/ADR-015-freshness-requirements-v2-and-independent-discovery.md) (Direct Source Catalog, Workable/Pinpoint, no first-party adapter yet); [sources.md](../sources.md#direct-source-catalog-milestone-81-adr-015-6).

Date: 2026-10-05. Public repo: counts only, no listing data.

## Method and evidence rules

- Official evidence only: the company's own careers page, or a provider-hosted official page, tied to the board identifier. No third-party tracker or aggregator was used as evidence.
- One documented-API GET per board (Greenhouse Job Board API, Lever postings API, Ashby posting API, SmartRecruiters Posting API, Workable widget API, Pinpoint postings.json), run by the lead on 2026-10-05. Board postings and internship-title counts come from that run (word-boundary match on "intern") and supersede the research agents' counts.
- No undocumented/internal endpoints were called. robots.txt and sitemaps were read for first-party candidates only.
- Evidence strength: A = the company's careers page links or embeds the board, or job URLs sit on the company domain. B = provider API returns the company's own postings and indexed official board pages exist, but the careers page link was not visible (JS app or blocked). WEAK = platform claim from a search snippet only; not official evidence.
- Production open = approximate open opportunities matched by organization name (open total; ATS-backed / feed-only / with description). "-" = not in the tracked list.
- Internship counts are board-level (include non-US locations); they are not production numbers.

## Status legend

| Status | Meaning |
|---|---|
| DIRECT_SUPPORTED | Documented provider adapter exists AND the board is configured in production |
| DIRECT_SUPPORTED_NOT_CONFIGURED | In the Direct Source Catalog (verified); owner can add it to production config |
| GREEN_FIRST_PARTY_BUILD | Safe first-party adapter could be built now. None this milestone |
| YELLOW_RESEARCH_ONLY | Structured access exists but is undocumented or terms are unreviewed; do not build yet |
| FEED_FALLBACK | No supported direct path; covered only by the community discovery feed link-out |
| CURATED_ONLY | Hand-verified registry entries for named programs only |
| REJECT_AUTOMATION | robots/terms/bot-protection or project rule forbids automation |

Production configured direct sources today: Greenhouse akunacapital, morsecorpcoop, verkada, hpiq, coinbase, waymo, robinhood, devtechnology, dvtrading, lyft, advancedspace, singlestore, thenuclearcompany; Lever hermeus, kitware; Ashby ramp, bedrock-robotics, allen-control-systems, base-power, reflect-orbital; SmartRecruiters abbvie, boschgroup, eurofins, keenfinity, llnl, wellmarkinc. New this milestone: Workable and Pinpoint adapters (documented keyless APIs).

## Company matrix (87 companies)

| Company | Careers URL | Platform (evidence) | Status | provider:identifier | Board postings / internship titles (lead-verified) | Production open (ATS / feed-only / with description) | Reason | Next action |
|---|---|---|---|---|---|---|---|---|
| Netflix | jobs.netflix.com | Eightfold PCSX (A: page source) | YELLOW_RESEARCH_ONLY | - | - | 0 (0/0/0) | Sitemap + JobPosting JSON-LD; terms not reviewed | First-party card #1 |
| Microsoft | careers.microsoft.com -> apply.careers.microsoft.com | Eightfold PCSX (A) | YELLOW_RESEARCH_ONLY | - | - | 0 (0/0/0) | Same adapter as Netflix; sitemap completeness and terms unverified | First-party card #2 |
| Apple | jobs.apple.com | In-house (A) | YELLOW_RESEARCH_ONLY | - | - | 0 (0/0/0) | Sitemap only, no JSON-LD; robots 404 | First-party card #3 |
| Meta | metacareers.com/jobs | In-house (A) | REJECT_AUTOMATION | - | - | 0 (0/0/0) | robots notice forbids automated collection without written permission | None (needs written permission) |
| Amazon | amazon.jobs | In-house SPA (A) | YELLOW_RESEARCH_ONLY | - | - | 9 (0/9/0) | Undocumented search XHR only; no sitemap | Feed link-out |
| Google | google.com/about/careers/applications | In-house (A) | REJECT_AUTOMATION | - | - | 0 (0/0/0) | robots disallows jobs result paths | None |
| Adobe | careers.adobe.com | Phenom + Workday apply links (A) | FEED_FALLBACK | - | - | 0 (0/0/0) | Unsupported ATS | Feed link-out |
| Dropbox | dropbox.jobs | Greenhouse (B: job id match) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:dropbox | 39 / 0 | 0 (0/0/0) | 0 intern titles now | Owner may add |
| GitHub | github.careers | iCIMS (A) | FEED_FALLBACK | - | - | 0 (0/0/0) | Greenhouse `github` 404 | Feed link-out |
| Salesforce | salesforce.com/company/careers | Workday probable (WEAK: not official evidence) | FEED_FALLBACK | - | - | 0 (0/0/0) | ATS unconfirmed | Feed link-out |
| Scale AI | scale.com/careers; labs.scale.com/jobs | Greenhouse (A via labs.scale.com) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:scaleai | 192 / 3 | 1 (0/1/0) | - | Owner may add |
| Spotify | lifeatspotify.com/jobs | Lever (A: official page names board) | DIRECT_SUPPORTED_NOT_CONFIGURED | lever:spotify | 82 / 1 | 0 (0/0/0) | - | Owner may add |
| Oracle | careers.oracle.com | Oracle Recruiting Cloud (A) | FEED_FALLBACK | - | - | 0 (0/0/0) | No documented external API | Feed link-out |
| PayPal | careers.pypl.com | Eightfold (A) | FEED_FALLBACK | - | - | 0 (0/0/0) | Unsupported ATS | Feed link-out |
| Bloomberg | bloomberg.com/company/careers | Avature (A) | FEED_FALLBACK | - | - | 0 (0/0/0) | Unsupported ATS | Feed link-out |
| Cisco | careers.cisco.com | Phenom (A) | FEED_FALLBACK | - | - | 6 (0/6/0) | Unsupported ATS | Feed link-out |
| Jane Street | janestreet.com/join-jane-street/open-roles | Greenhouse behind custom front end (A: absolute_url on janestreet.com) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:janestreet | 230 / 0 | 0 (0/0/0) | 0 intern titles now (campus recruiter only) | Owner may add |
| Waymo | careers.withwaymo.com | Greenhouse (A) | DIRECT_SUPPORTED | greenhouse:waymo | 364 / 45 | 45 (45/0/45) | Configured | Maintain |
| Lyft | lyft.com/careers | Greenhouse via CareerPuck front end (A) | DIRECT_SUPPORTED | greenhouse:lyft | 193 / 19 | 19 (19/0/19) | Configured | Maintain |
| Uber | jobs.uber.com | Oracle Cloud HCM (A) | FEED_FALLBACK | - | - | 0 (0/0/0) | Greenhouse `uber` 404 | Feed link-out |
| DoorDash | careersatdoordash.com | Greenhouse (B: careers site 403; ownership via API company_name DoorDash USA) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:doordashusa | 458 / 4 | 2 (0/2/0) | Ownership caveat: careers page link not confirmed | Owner may add |
| Airbnb | careers.airbnb.com | Greenhouse (A: embed in page source) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:airbnb | 151 / 0 | 0 (0/0/0) | 0 intern titles now | Owner may add |
| Instacart | instacart.careers | Greenhouse (A: embed in page source) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:instacart | 131 / 0 | 0 (0/0/0) | 0 intern titles now | Owner may add |
| Pinterest | pinterestcareers.com | Greenhouse (A: gh_jid links) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:pinterest | 167 / 12 | 3 (0/3/0) | Some non-US locations | Owner may add |
| Snap | careers.snap.com | Workday (A) | FEED_FALLBACK | - | - | 0 (0/0/0) | Workday CXS undocumented | Feed link-out |
| NVIDIA | jobs.nvidia.com/careers | Eightfold PCSX (A) | CURATED_ONLY | - | - | 2 (0/2/0) | robots Disallow / with allow-list; /api/pcsx undocumented, not called; no sitemap | Curated Intern Program + Ignite entries |
| AMD | careers.amd.com | iCIMS (A) | FEED_FALLBACK | - | - | 0 (0/0/0) | Sitemap has ids only | Curated student-programs entry (page unread) |
| Intel | jobs.intel.com | Workday (A: redirect) | REJECT_AUTOMATION | - | - | 4 (0/4/0) | Workday internal API excluded by project rule | Curated link-out only if stable page found |
| Qualcomm | careers.qualcomm.com | Eightfold (A) | FEED_FALLBACK | - | - | 0 (0/0/0) | No documented feed | Feed link-out |
| Broadcom | broadcom.com/company/careers | Workday (WEAK: search result only) | FEED_FALLBACK | - | - | 0 (0/0/0) | Platform unverified | Manual browser re-verify |
| Marvell | marvell.com/company/careers.html | Workday (WEAK: snippet; site 403) | FEED_FALLBACK | - | - | 4 (0/4/0) | Platform unverified | Manual re-verify |
| Micron | careers.micron.com | Eightfold (A) | YELLOW_RESEARCH_ONLY | - | - | 7 (0/7/0) | Robots-listed sitemap (~500 URLs); no JSON-LD seen | First-party card #7 |
| Texas Instruments | careers.ti.com | Oracle Cloud HCM (moderate) | FEED_FALLBACK | - | - | 6 (0/6/0) | Unsupported | Feed link-out |
| Arm | careers.arm.com | iCIMS (A) | FEED_FALLBACK | - | - | 0 (0/0/0) | Unsupported | Feed link-out |
| Applied Materials | careers.appliedmaterials.com | Eightfold (A) | FEED_FALLBACK | - | - | 1 (0/1/0) | Unsupported | Feed link-out |
| Lam Research | careers.lamresearch.com | Eightfold (A) | FEED_FALLBACK | - | - | 0 (0/0/0) | Unsupported | Feed link-out |
| KLA | kla.com/careers | Workday (WEAK: search; official page denied) | FEED_FALLBACK | - | - | 4 (0/4/0) | Unsupported | Feed link-out |
| ASML | asml.com/en/careers | Not determined | FEED_FALLBACK | - | - | 0 (0/0/0) | Platform undisclosed | Feed link-out |
| Synopsys | careers.synopsys.com | Avature (A) | FEED_FALLBACK | - | - | 0 (0/0/0) | Unsupported | Feed link-out |
| Cadence | cadence.com careers | Workday (WEAK: search; page 403) | FEED_FALLBACK | - | - | 0 (0/0/0) | Unsupported | Feed link-out |
| Analog Devices | analog.com/en/careers.html | Workday (WEAK: search; page timed out) | FEED_FALLBACK | - | - | 0 (0/0/0) | Unsupported | Feed link-out |
| Microchip | microchip.com/en-us/about/careers | In-house main site; separate SmartRecruiters `Microchip` board (9 postings, San Jose/Boulder, 0 interns) | FEED_FALLBACK | - | - | 1 (0/1/0) | SR board deliberately NOT cataloged: partial regional subset, 0 internships | Feed link-out |
| Tesla | tesla.com/careers | In-house; 403 to fetchers | REJECT_AUTOMATION | - | - | 0 (0/0/0) | Bot-blocked; no headless scraping | Feed link-out |
| SpaceX | spacex.com/careers | Greenhouse (B) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:spacex | 2645 / 15 | 0 (0/0/0) | Large board (2.6k); content fetch cost | Owner may add |
| Anduril | anduril.com/careers | Greenhouse `andurilindustries` (B) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:andurilindustries | 2442 / 20 | 2 (0/2/0) | Large board (2.4k) | Owner may add |
| Boston Dynamics | bostondynamics.com/careers | Workday (A) | FEED_FALLBACK | - | - | - | Unsupported | Feed link-out |
| Skydio | skydio.com/careers | Ashby (A: job ids match) | DIRECT_SUPPORTED_NOT_CONFIGURED | ashby:skydio | 144 / 8 | 1 (0/1/0) | - | Owner may add |
| Nuro | nuro.ai/careers | Greenhouse (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:nuro | 102 / 2 | - | - | Owner may add |
| Aurora Innovation | aurora.tech/careers | Not identified | FEED_FALLBACK | - | - | - | Slugs probed 404; do not guess | Browser inspection later |
| Zoox | zoox.com/careers | Lever (B) | DIRECT_SUPPORTED_NOT_CONFIGURED | lever:zoox | 234 / 0 | - | 0 intern titles now | Owner may add |
| Rivian | careers.rivian.com | iCIMS (A) | FEED_FALLBACK | - | - | - | Unsupported | Feed link-out |
| Lucid Motors | lucidmotors.com/careers | Greenhouse (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:lucidmotors | 437 / 0 | - | 0 intern titles now | Owner may add |
| Western Digital | careers.smartrecruiters.com/WesternDigital | SmartRecruiters (B) | DIRECT_SUPPORTED_NOT_CONFIGURED | smartrecruiters:westerndigital | 318 / 4 | - | Agent S9 counted 35 interns; lead count 4 supersedes | Owner may add |
| Seagate | seagatecareers.com | SuccessFactors (A) | FEED_FALLBACK | - | - | - | Unsupported | Feed link-out |
| NXP | nxp.wd3.myworkdayjobs.com | Workday (A) | FEED_FALLBACK | - | - | - | Unsupported | Feed link-out |
| Skyworks | careers.skyworksinc.com | SuccessFactors (A) | FEED_FALLBACK | - | - | - | Unsupported | Feed link-out |
| Qorvo | qorvo.com/about-us/careers | Not identified (429) | FEED_FALLBACK | - | - | - | Unverified | Low priority |
| GlobalFoundries | globalfoundries.wd1.myworkdayjobs.com | Workday (A) | FEED_FALLBACK | - | - | - | Unsupported | Feed link-out |
| Samsung Semiconductor US | sec.wd3.myworkdayjobs.com | Workday (A) | FEED_FALLBACK | - | - | - | Unsupported | Feed link-out |
| SK hynix America | skhynixamerica.com/careers | Not verified (unreachable) | FEED_FALLBACK | - | - | - | Unverified | Low priority |
| Lockheed Martin | lockheedmartinjobs.com | Eightfold (A) | FEED_FALLBACK | - | - | - | Undocumented API | Feed link-out |
| Northrop Grumman | northropgrumman.com/careers | Eightfold (A) | FEED_FALLBACK | - | - | - | Undocumented API | Feed link-out |
| RTX | careers.rtx.com | Phenom (A) | FEED_FALLBACK | - | - | - | Unsupported | Feed link-out |
| Intuitive Surgical | careers.intuitive.com | SmartRecruiters (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | smartrecruiters:intuitive | 746 / 0 | - | 0 intern titles now | Owner may add |
| Cerebras Systems | cerebras.ai/open-positions | Ashby (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | ashby:cerebras | 117 / 0 | - | 0 intern titles now | Owner may add |
| SambaNova Systems | sambanova.ai/company/careers | Greenhouse `sambanovasystems` (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:sambanovasystems | 63 / 0 | - | 0 intern titles now | Owner may add |
| Groq | groq.com | Gem (B: search only) | FEED_FALLBACK | - | - | - | Gem unsupported | Feed link-out |
| Tenstorrent | tenstorrent.com/careers | Greenhouse (B) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:tenstorrent | 129 / 0 | - | 0 intern titles now | Owner may add |
| SiFive | sifive.com/careers | Workday (A) | FEED_FALLBACK | - | - | - | Unsupported | Feed link-out |
| Palantir | palantir.com/careers/students-and-early-talent | Lever (B: indexed official student page) | DIRECT_SUPPORTED_NOT_CONFIGURED | lever:palantir | 319 / 45 | 0 (0/0/0) | High intern yield | Owner may add (priority) |
| Citadel / Citadel Securities | citadel.com/careers | In-house; 403 | REJECT_AUTOMATION | - | - | - | Bot-blocked | Feed link-out |
| Hudson River Trading | hudsonrivertrading.com/careers | In-house; only talent-community Greenhouse board (not cataloged) | FEED_FALLBACK | - | - | - | No complete official board | Feed link-out |
| OpenAI | openai.com/careers | Ashby (B: careers 403 to fetchers; ownership via Ashby API `openai`) | DIRECT_SUPPORTED_NOT_CONFIGURED | ashby:openai | 828 / 0 | 0 (0/0/0) | - | Owner may add |
| Anthropic | anthropic.com/careers | Greenhouse (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:anthropic | 638 / 0 | 0 (0/0/0) | 0 intern titles now | Owner may add |
| Databricks | databricks.com/company/careers | Greenhouse (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:databricks | 888 / 11 | 0 (0/0/0) | - | Owner may add |
| Cloudflare | cloudflare.com/careers | Greenhouse (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:cloudflare | 405 / 1 | 0 (0/0/0) | - | Owner may add |
| Stripe | stripe.com/jobs | Greenhouse (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:stripe | 718 / 14 | 2 (0/2/0) | - | Owner may add |
| Snowflake | careers.snowflake.com | Phenom front end; listings link jobs.ashbyhq.com/snowflake (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | ashby:snowflake | 348 / 5 | 0 (0/0/0) | - | Owner may add |
| MongoDB | mongodb.com/careers | Greenhouse (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:mongodb | 389 / 0 | 0 (0/0/0) | 0 intern titles now | Owner may add |
| Datadog | careers.datadoghq.com | Greenhouse (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:datadog | 442 / 8 | 1 (0/1/0) | - | Owner may add |
| Figma | figma.com/careers | Greenhouse (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:figma | 162 / 7 | 3 (0/3/0) | - | Owner may add |
| Coinbase | coinbase.com/careers | Greenhouse (A) | DIRECT_SUPPORTED | greenhouse:coinbase | 229 / 27 | 27 (27/0/27) | Configured | Maintain |
| Reddit | redditinc.com/careers | Greenhouse (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | greenhouse:reddit | 152 / 0 | 0 (0/0/0) | 0 intern titles now | Owner may add |
| Impulse Space | impulsespace.com/careers (Pinpoint) | Pinpoint (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | pinpoint:impulsespace | 204 / 26 | 0 (0/0/0) | No posted date in API | Owner may add (priority) |
| Astrolab | astrolab.pinpointhq.com | Pinpoint (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | pinpoint:astrolab | 40 / 1 | - | No posted date in API | Owner may add |
| Sorting Robotics | apply.workable.com/sorting-robotics | Workable (A) | DIRECT_SUPPORTED_NOT_CONFIGURED | workable:sorting-robotics | 12 / 1 | - | - | Owner may add |
| Flexion Robotics | apply.workable.com/flexion-robotics | Workable (B: careers page did not link the board) | FEED_FALLBACK | workable:flexion-robotics | 8 / 1 | - | NOT cataloged: ownership unconfirmed | Confirm link, then catalog |

Status totals: CURATED_ONLY 1, DIRECT_SUPPORTED 3, DIRECT_SUPPORTED_NOT_CONFIGURED 33, FEED_FALLBACK 40, REJECT_AUTOMATION 5, YELLOW_RESEARCH_ONLY 5. The Direct Source Catalog holds 36 verified entries (3 configured + 33 not configured). Not cataloged on purpose: Microchip SmartRecruiters (partial regional subset, 0 internships) and Flexion Robotics Workable (careers page did not link the board).

## Coverage gap summary

Target universe = the 59 companies in the production company-coverage list (all 59 matched to a researched row; 10 further cataloged boards, e.g. Astrolab and Sorting Robotics, are outside that list). Production counts are approximate name matches.

| Measure | Count | Note |
|---|---|---|
| Target companies directly supported (configured) | 3 | Coinbase, Waymo, Lyft |
| Target companies direct-source configurable now (catalog, not configured) | 23 | owner can add; 8 of them already show feed-only rows, 15 are absent |
| Catalog entries not configured, all (incl. outside target list) | 33 | |
| Target companies with feed-only rows (open > 0, 0 ATS-backed) | 18 | 8 are configurable now; 10 have no direct path |
| Target companies completely absent from production (0 open) | 38 | 15 are configurable now; 23 have no direct path |

## First-party adapter candidates (ranked)

No first-party adapter was built this milestone: every candidate is YELLOW or worse. All rows: terms of use not reviewed unless stated; no tracker evidence.

| Rank | Company | Status | Why next |
|---|---|---|---|
| 1 | Netflix | YELLOW | Eightfold; robots-advertised sitemap, JSON-LD; smallest (4 intern slugs of 472) |
| 2 | Microsoft | YELLOW | Same Eightfold adapter; best value (71 intern slugs of 2307) |
| 3 | Apple | YELLOW | Sitemap with lastmod; no JSON-LD |
| 4 | Meta | REJECT | robots notice prohibits automated collection |
| 5 | Amazon | YELLOW (in practice feed) | Undocumented XHR only |
| 6 | NVIDIA | CURATED_ONLY | Eightfold, internal API only |
| 7 | Micron | YELLOW | Robots-listed sitemap, no JSON-LD seen |

Google is REJECT_AUTOMATION (robots disallows the jobs result paths) and is not carded.

### Implementation cards

| | Netflix | Microsoft | Apple | Meta | Amazon | NVIDIA | Micron |
|---|---|---|---|---|---|---|---|
| Endpoint shape | robots-listed `sitemap_index.xml` -> sitemap (472 URLs) -> job page JSON-LD | `/careers/sitemap.xml?domain=microsoft.com` (2307 URLs) -> job page JSON-LD | `sitemap-index.xml` -> en-us sitemap (4513 URLs, per-URL lastmod) -> HTML detail | `/jobsearch/sitemap.xml` (1071 URLs, no titles) -> JSON-LD | none documented; SPA over undocumented search endpoint | `/api/pcsx` internal API (not called); no sitemap | robots-listed sitemap (~500 URLs) -> rendered page |
| Robots | Disallow / with allow-list incl. /careers; Sitemap line present | same allow-list; sitemap NOT referenced in robots | jobs.apple.com/robots.txt 404 | `/profile/` not disallowed but header forbids automated collection without written permission | disallows /internal only | Disallow / with allow-list incl. /api/pcsx; no Sitemap | same allow-list; Sitemap line present |
| Terms status | not reviewed | not reviewed | not reviewed | explicit prohibition | not reviewed | not reviewed | not reviewed |
| Closure semantics | URL leaves sitemap (validThrough is synthetic ~6 months, ignore) | URL leaves sitemap; completeness unverified | URL leaves sitemap | no validThrough; absence only | none sanctioned | n/a | URL leaves sitemap; unproven |
| Why not GREEN now | Terms unreviewed; sitemap is for search engines, not a developer interface | Terms unreviewed; sitemap completeness unverified; unadvertised | No structured detail; sitemap unadvertised | Explicit anti-automation notice | Undocumented endpoint only | Undocumented internal API; no feed | No structured fields; descriptions need rendered-page scraping |
| What makes it GREEN | Written terms review allowing it; low concurrency; slug-filtered fetch | Verify completeness vs real inventory + terms; reuse Netflix adapter | Confirm JSON-LD or stable HTML contract + terms | Written permission from Meta | Published API or feed | Published XML feed or API | Verified JSON-LD or stable contract + terms |

## ATS ecosystem (S6)

Dates and counts as of 2026-10-05. Claims from search snippets are marked.

| Family | Public no-auth documented postings endpoint | Class | Note |
|---|---|---|---|
| Workable | Yes: `GET https://www.workable.com/api/accounts/{subdomain}?details=true` (redirects to apply.workable.com widget API) | GREEN, built this milestone | No documented rate limit or third-party terms; kill-switch flag advised |
| Pinpoint | Yes: `https://{sub}.pinpointhq.com/postings.json` | GREEN, built this milestone | No posted date (use first_seen, labeled); large payloads |
| Rippling | Partly: list endpoint documented (snippet), keyless 200 observed; list has no description/date; detail endpoint docs unverified | YELLOW, near-GREEN | N+1 detail fetches; largest feed footprint |
| Teamtailor | Partly: RSS is a help-center feature; JSON API needs token | YELLOW | Customer domains; EU-heavy |
| Personio | Partly: XML feed, docs unreadable (snippet) | YELLOW | EU/DACH-centric |
| Breezy HR | `/json` works keyless but undocumented | YELLOW | Research only |
| Recruitee | Public API documented but token required from 2027-02-10 | RED | Do not build |
| BambooHR, JazzHR | No public postings API / key per customer | RED | |
| Jobvite, iCIMS, Oracle, Workday, SuccessFactors | No documented public API / authenticated; Workday excluded by project policy | RED | Feed link-out |
| Eightfold, Phenom | OAuth only (clients) | RED | Feed link-out |

Feed-only application URL classes in production today (feed-only open items, approximate): workday 593, oracle 147, greenhouse 127, ashby 41, other/custom 26, smartrecruiters 20, lever 20, rippling 11, workable 8, breezy 4.

## Programs and government (S7 summary)

| Source | Structured source? | Class |
|---|---|---|
| NASA OSTEM / STEM Gateway | None documented | CURATED_ONLY (recheck Jan 2027) |
| DOE SULI | None | CURATED_ONLY |
| Zintellect / ORISE | No API/RSS; terms unread | YELLOW_RESEARCH_ONLY (link out) |
| NSF REU directory | No export; ETAP robots disallows crawling | CURATED_ONLY / REJECT_AUTOMATION |
| National labs | No new Greenhouse/Lever/Ashby lab found | FEED_FALLBACK / CURATED_ONLY |
| USAJOBS Search API | Documented but key-gated (free key, owner-held secret); terms/rate guide not fully read | YELLOW until a separate owner-key ADR |

Structured sources: none GREEN. Registry candidates (7, by name): NIH Summer Internship Program, Fermilab PRISM, ONR SEAP, NIST SHIP, PNNL High School Research Internship, Sandia High School Internships, NASA Solar System Ambassadors. Flagged rechecks: (1) NASA OSTEM, recheck Jan 2027; (2) Google STEP and Microsoft Explore, no entry (official pages not retrievable), recheck fall 2027. Also note: ONR SEAP deadline conflicts with an NRL search excerpt (Nov 30 vs Nov 1), verify before publishing. USAJOBS needs its own ADR before any build.

## Independent discovery potential

Sum of internship-title counts (lead-verified) on the 33 cataloged boards not yet configured: **188**. This is an architecture capability if the owner adds those boards. It is NOT a production number: board counts include non-US locations and are a point-in-time API total, not what would be matched, deduplicated or retained by the app.
