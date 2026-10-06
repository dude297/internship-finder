# Direct Source Expansion and Provider Research

> **Research only (non-normative).** Date: 2026-10-06. Last verified: 2026-10-06.
> Used by / superseded by: `backend/data/direct_source_catalog.json` (the 28 catalog-ready candidates with current intern postings added 2026-10-06, each re-verified against its provider's documented API the same day); extends [direct-company-source-matrix.md](direct-company-source-matrix.md).

Official evidence only (company careers pages and providers' documented public APIs); no tracker data. Intern counts are board-wide title matches on 2026-10-06, not production numbers.

Method: live GET of each provider's documented public API (Greenhouse, Lever, Ashby, SmartRecruiters, Pinpoint) on 2026-10-06 with a research User-Agent; careers pages fetched where reachable to look for the provider link. Intern count = title word-boundary match on intern/internship/co-op (board-wide, includes non-US and non-technical interns, not a production number).

Evidence class: A = careers page links the board; B = API returns the company's own postings and the board name/links match, but the careers page link was not visible to a plain fetch (JS app or 403).

Honesty notes:
- Workable: my own probing got me rate-limited (HTTP 429 / Cloudflare 1015), so NO Workable board was re-verified today (Sorting Robotics shows the 2026-10-05 matrix figure of 12 postings / 1 intern only). No new Workable candidates.
- Pinpoint: slugs like `arm`, `synopsys`, `zoox`, `elastic`, `hermeus`, `amplitude` return 2-5 generic postings ("Head of DEI - UK") = unrelated or demo tenants. Rejected as not official. Only the already-cataloged `impulsespace` and `astrolab` are real (206 / 39 postings).
- Rippling docs and Recruitee notice were read through search snippets, not the primary pages (JS-rendered / PDF).

## Goal A: requested companies

### Already cataloged (nothing new; live counts today)
Anthropic gh 644/0, Databricks gh 887/11, Cloudflare gh 415/4, Stripe gh 719/14, MongoDB gh 392/0, Figma gh 162/8, Reddit gh 151/0, OpenAI ashby 823/0, Snowflake ashby 350/5, Waymo gh 361/47 (configured), Lyft gh 189/19 (configured), DoorDash gh:doordashusa 459/4, Airbnb gh 151/0, Skydio ashby 152/8, Anduril gh:andurilindustries 2457/25. Format total/intern.

### Not on a supported provider (provider-first probes today were all negative)
| Company | Platform | Class | Reason |
|---|---|---|---|
| Amazon | In-house SPA | YELLOW | undocumented search XHR only |
| Apple | In-house | YELLOW | sitemap only |
| Google | In-house | RED | robots disallows job paths |
| Meta | In-house | RED | robots notice forbids automation |
| Microsoft, Netflix | Eightfold PCSX | YELLOW | sitemap + JSON-LD, terms unreviewed |
| NVIDIA | Eightfold | YELLOW | robots Disallow /, undocumented API |
| AMD, Arm | iCIMS | YELLOW | no documented API |
| Intel, Boston Dynamics | Workday | RED | Workday excluded by project rule |
| Qualcomm, Applied Materials, Lam | Eightfold | YELLOW | no documented API |
| Broadcom, Marvell, KLA, Cadence, ADI | Workday (unverified) | YELLOW | platform unverified |
| Micron | Eightfold | YELLOW | sitemap, no structured fields |
| Texas Instruments, Uber | Oracle HCM | YELLOW | no documented API |
| ASML | undetermined | YELLOW | undisclosed |
| Synopsys | Avature | YELLOW | no documented API |
| Tesla | In-house | RED | bot-blocked |
| Aurora Innovation | not identified | YELLOW | no board found |
Platform column is carried forward from docs/research/direct-company-source-matrix.md (2026-10-05); today I only re-confirmed that no supported-provider board exists under the obvious slugs.

### New verified candidates (33 catalog-ready, plus 2 needing a browser check)
All have verified_at 2026-10-06, API HTTP 200. Tags from the catalog's fixed set. Counts total/intern now.

| Organization | kind:identifier | Careers URL | Tags | Postings / interns | Ev. | Note |
|---|---|---|---|---|---|---|
| Rocket Lab | greenhouse:rocketlab | rocketlabcorp.com/careers/ | aerospace, hardware | 559 / 96 | B | board name "Rocket Lab Corporation" |
| Astranis | greenhouse:astranis | astranis.com/careers | aerospace, hardware | 182 / 58 | A | embeds board |
| Zipline | greenhouse:flyzipline | zipline.com/careers | robotics, aerospace, hardware | 349 / 86 | B | many interns are non-engineering |
| Varda Space Industries | greenhouse:vardaspace | varda.com/careers/ | aerospace, hardware | 105 / 27 | B | |
| Neuralink | greenhouse:neuralink | neuralink.com/careers/ | hardware, research, robotics | 78 / 18 | B | analog/digital IC design interns |
| Figure AI | greenhouse:figureai | figure.ai/careers | robotics, ai | 85 / 3 | B | do NOT use slug `figure` (Figure Lending) |
| Kodiak Robotics | greenhouse:kodiak | kodiak.ai/careers | mobility, robotics, ai | 69 / 6 | A | |
| PsiQuantum | greenhouse:psiquantum | psiquantum.com/careers | hardware, research | 75 / 6 | B | |
| Lightmatter | greenhouse:lightmatter | lightmatter.co/careers/ | ai, hardware, semiconductor | 68 / 2 | B | photonic chips |
| Astera Labs | greenhouse:asteralabs | asteralabs.com/careers/ | semiconductor, hardware, cloud | 182 / 2 | A | |
| Formlabs | greenhouse:formlabs | careers.formlabs.com | hardware | 233 / 13 | B | gh_jid links on careers site |
| Together AI | greenhouse:togetherai | together.ai/careers | ai, cloud | 78 / 11 | A | careers page calls the board API |
| Samsara | greenhouse:samsara | samsara.com/company/careers | cloud, hardware, software | 242 / 5 | B | interns mostly sales |
| Kairos Power | greenhouse:kairospower | kairospower.com/careers/ | research, hardware | 33 / 5 | A | |
| Roblox | greenhouse:roblox | careers.roblox.com | software | 255 / 3 | B | |
| Efficient Computer | greenhouse:efficientcomputer | efficient.computer/careers | semiconductor, hardware | 20 / 1 | B | careers URL 404 on fetch, check |
| Motional | greenhouse:motional | motional.com/careers | mobility, robotics, ai | 73 / 1 | B | |
| Apptronik | greenhouse:apptronik | apptronik.com/careers | robotics, hardware | 79 / 0 | B | watch only |
| Agility Robotics | greenhouse:agilityrobotics | agilityrobotics.com/careers | robotics, hardware | 78 / 0 | A | watch only |
| Relativity Space | greenhouse:relativity | relativityspace.com/careers | aerospace, hardware | 348 / 0 | B | watch only |
| Epic Games (browser check) | greenhouse:epicgames | epicgames.com/site/en-US/careers | software | 145 / 22 | B | careers 403 to fetch |
| Rubrik (browser check) | greenhouse:rubrik | rubrik.com/company/careers | cloud, software | 129 / 5 | B | careers 403 to fetch |
| Shield AI | lever:shieldai (global) | shield.ai/careers/ | aerospace, robotics, ai | 594 / 6 | A | jobs.lever.co/shieldai; co-op titles included |
| Waabi | lever:waabi (global) | waabi.ai/careers/ | mobility, robotics, ai | 92 / 2 | A | PhD research intern |
| Quantinuum | lever:quantinuum (eu) | quantinuum.com/careers | research, hardware | 124 / 16 | A | EU Lever host, mixed UK/US |
| Rigetti Computing | lever:rigetti (global) | rigetti.com/careers | research, hardware | 16 / 1 | A | |
| Mobileye | lever:mobileye (eu) | mobileye.com/careers/ | mobility, ai, semiconductor | 180 / 0 | B | Israel-heavy; watch only |
| Etched | ashby:etched | etched.com/careers | ai, hardware, semiconductor | 108 / 16 | A | |
| Saronic | ashby:saronic | saronic.com/careers | aerospace, robotics, ai | 207 / 10 | A | EE intern titles |
| Gecko Robotics | ashby:gecko-robotics | geckorobotics.com/careers | robotics, hardware | 23 / 4 | A | |
| Cohere | ashby:cohere | cohere.com/careers | ai | 135 / 3 | A | SWE and research Winter 2027 |
| Notion | ashby:notion | notion.com/careers | software | 135 / 4 | A | |
| 1X Technologies | ashby:1x | 1x.tech/careers | robotics, ai, hardware | 95 / 2 | A | |
| Helion Energy | ashby:helion | helionenergy.com/careers/ | research, hardware | 69 / 6 | A | |
| d-Matrix | ashby:d-matrix | d-matrix.ai/careers/ | ai, hardware, semiconductor | 34 / 0 | A | watch only |

Full evidence strings, sample intern titles in `catalog-candidates.json`. Not catalog-ready (ownership unconfirmed, left out): Perplexity ashby:perplexity (129/4, careers 403), Wayve ashby:wayve (138/0, careers 403), Physical Intelligence ashby:physicalintelligence (37/2, careers 429), xAI greenhouse:xai (board name "SpaceXAI", 302/4, ownership/naming changed), Cruise etc. not found. Already production-configured so excluded: Verkada, Robinhood, Hermeus, Ramp, Base Power.

## Goal B: provider families
| Provider | Class | Key facts |
|---|---|---|
| Rippling | GREEN (conditional) | Official "Recruiting Job Board" doc (developer.rippling.com/documentation/job-board-api). `api.rippling.com/platform/api/ats/v1/board/{slug}/jobs` keyless 200; list: uuid, name, department, url, workLocation; NO description or date, NOT paginated (page params ignored; 657 rows for `rippling`); detail `/jobs/{uuid}` has description, createdOn, employmentType (N+1). Fixed host. Closure by absence from full list. Verified tenants: `rippling` (9 intern titles), `walden-robotics` seen via search. Only 1 verified tenant I could probe, 3+ tech employers NOT demonstrated; probed ~20 guessed slugs (roboforce, anysphere, saronic, ...): all 404. |
| Teamtailor | GREEN, only `*.teamtailor.com` | Help-center doc: `{site}/jobs.rss`, public, offset/per_page (100 default), global id, description, pubDate. Verified: Tobii, Starship Technologies (robots), Axis, Polestar, Bambuser. Custom domains must be excluded. JSON API keyed. EU-heavy. |
| Personio | YELLOW | Documented XML (developer.personio.de/v1.0/reference/get_xml), `{co}.jobs.personio.de/xml`, ids, full snapshot. Heavy 429s (12 of 17 tenants) and no documented limits. Tenants: Neura Robotics, Wandelbots, Personio. EU only. |
| Breezy HR | YELLOW | `{co}.breezy.hr/json` keyless but undocumented (official docs only keyed v3). |
| Recruitee | RED | Public offers API documented but token required from 2027-02-10 (Tellent notice, via search). |
| JazzHR | RED | Customer-minted API key. |
| BambooHR | RED/YELLOW | `/careers/list` undocumented widget endpoint. |
| Jobvite | RED | key+secret. |

Rippling feed-only postings (11) cannot be converted into ATS-backed ones until tenants are identified; consider matching their `ats.rippling.com/{slug}` URLs from the existing feed rows to extract slugs (a repo-side query, not done here).

## Goal C: ranking for activation

Scoring: student relevance (EE/CompE/CS/AI/semis/hardware/robotics/research) > live intern count > description availability > provider reliability > runtime cost. Provider cost notes: Greenhouse (list; content needs `content=true` or per-job, cheap), Lever (list includes descriptions, 1 request), Ashby (list includes descriptions, 1 request), Pinpoint (1 request, large payload, no posted date), SmartRecruiters (list + per-posting detail = costliest). Large boards (Anduril 2.5k, SpaceX 2.7k, Shield AI 0.6k) cost more fetch/storage but Internships-only scope bounds what is kept.

Currently configured catalog entries: Waymo, Lyft, Coinbase (production total: 13 GH, 2 Lever, 5 Ashby, 6 SR; the others are not catalog entries: akunacapital, morsecorpcoop, verkada, hpiq, robinhood, devtechnology, dvtrading, advancedspace, singlestore, thenuclearcompany, hermeus, kitware, ramp, bedrock-robotics, allen-control-systems, base-power, reflect-orbital, abbvie, boschgroup, eurofins, keenfinity, llnl, wellmarkinc; from the matrix and m7/m8 release notes).

### Batch 1 (10)
| # | kind:identifier | Interns / total | Why |
|---|---|---|---|
| 1 | lever:palantir | 45 / 318 | CS/AI, highest-yield existing entry, Lever lists carry descriptions, cheap |
| 2 | greenhouse:rocketlab | 96 / 559 | EE/hardware/aerospace intern titles (Additive Mfg, avionics) |
| 3 | greenhouse:andurilindustries | 25 / 2457 | hardware/robotics/EE early-career; big board, accepted cost |
| 4 | pinpoint:impulsespace | 26 / 206 | aerospace hardware; no posted date caveat |
| 5 | greenhouse:astranis | 58 / 182 | RF/antenna/EE interns, small board, careers page links board (A) |
| 6 | greenhouse:flyzipline | 86 / 349 | robotics/drones/embedded; many non-eng interns, still strong |
| 7 | greenhouse:neuralink | 18 / 78 | analog/digital IC design interns, small board |
| 8 | greenhouse:vardaspace | 27 / 105 | aerospace engineering internships |
| 9 | greenhouse:databricks | 11 / 887 | AI/data/CS, big household name |
| 10 | ashby:etched | 16 / 108 | AI chip design/verification interns, Ashby 1-request |

### Batch 2 (10)
| kind:identifier | Interns / total | Why |
|---|---|---|
| ashby:skydio | 8 / 152 | drones/robotics, Ashby cheap |
| greenhouse:spacex | 12 / 2665 | hardware/EE; biggest board, lower yield per posting |
| ashby:saronic | 10 / 207 | EE/robotics interns, A evidence |
| lever:shieldai | 6 / 594 | aerospace/robotics, co-op titles, Lever cheap |
| greenhouse:formlabs | 13 / 233 | hardware/EE interns |
| greenhouse:stripe | 14 / 719 | CS/SWE interns |
| greenhouse:togetherai | 11 / 78 | AI research interns, small board |
| greenhouse:figureai | 3 / 85 | humanoid robotics (EE intern), small board |
| greenhouse:psiquantum | 6 / 75 | quantum hardware/research, small |
| ashby:cohere | 3 / 135 | AI SWE/research Winter 2027 |

Watchlist (next after Batch 2): smartrecruiters:westerndigital (4 / 329, semis, per-posting detail cost, many non-US), lever:waabi (2 / 92), greenhouse:kodiak (6 / 69), lever:quantinuum eu (16 / 124), ashby:notion (4), ashby:helion (6), greenhouse:figma (8 / 162), greenhouse:datadog (8), greenhouse:pinterest (13 / 174, some non-US). Zero-intern boards (Anthropic, OpenAI, MongoDB, Reddit, Airbnb, Instacart, Jane Street, Dropbox, Lucid, Cerebras, SambaNova, Tenstorrent, Zoox, Intuitive) are low value today; revisit in the fall hiring cycle.

Catalog gap: 33 of these candidates are not in `backend/data/direct_source_catalog.json`; adding them is an edit to that file plus the usual docs sync (not performed here). Apptronik, Agility, Relativity, d-Matrix, Mobileye have 0 interns now and are included only as watch entries.
