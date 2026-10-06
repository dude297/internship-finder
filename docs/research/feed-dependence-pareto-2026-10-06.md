# Feed Dependence Pareto and Direct Source Gap

> **Research only (non-normative).** Date: 2026-10-06. Last verified: 2026-10-06.
> Used by / superseded by: `backend/data/direct_source_catalog.json` (26 boards added from this analysis, 64 to 90 entries; none enabled); `backend/scripts/feed_pareto.py` (re-runnable). Extends [direct-source-expansion-2026-10-06.md](direct-source-expansion-2026-10-06.md).

## Method and approximations

- **Data:** the public community feed the app ingests (`zshah-tech-internships`), fetched once read-only on 2026-10-06 (`generated_at` 2026-10-06T11:05:24Z): **1,126 listings**. No production database access. It is the feed as published now, not production's open set.
- **Board identity:** each feed id names its ATS and board (`greenhouse:<board>:<id>`, `workday:<tenant>:...`, `oracle:<host>:<id>`); that identifier is matched first against catalog boards of the six supported providers (greenhouse, lever, ashby, smartrecruiters, workable, pinpoint), then the normalized company name against catalog organizations.
- **Enabled set (approximation):** the 45 production sources are reconstructed from [operations.md](../operations.md#milestone-9-11-release-train-measurements-2026-10-06) and the [release record](../releases/2026-10-06-m9-m11.md): 19 catalog boards activated 2026-10-06 (Anduril failed and is disabled) plus the 26 earlier configured boards named in the expansion research (Waymo, Lyft, Coinbase, and 23 non-catalog boards by slug, any provider). The slug list is a constant in the script. Matching is by slug regardless of provider kind, so a same-slug board on another provider would be misread as enabled; none is known.
- **Intern counts** are board-wide title matches (`intern`, `internship`, `co-op`) from each provider's public API on 2026-10-06, including non-US and non-technical roles. They are not production numbers.
- Relevance (H/M/L) is judged from titles for an EE/CompE/CS/AI/hardware student.

## Headline numbers (before the 26 new catalog entries)

| Feed status | Listings | % of 1,126 |
|---|---|---|
| Unsupported provider (Workday, Oracle HCM, Amazon, Rippling, Breezy) | 790 | 70.2% |
| Supported provider, board not in the catalog | 197 | 17.5% |
| DIRECT ACTIVE (board enabled in production; feed row is a duplicate) | 124 | 11.0% |
| DIRECT AVAILABLE (in the catalog, not enabled) | 15 | 1.3% |

The feed's dependence is dominated by two providers the app does not support: **Workday 617 (54.8%) and Oracle HCM 149 (13.2%)** = 766 listings (68.0%). Direct coverage of those needs a new adapter and a decision on ADR-level provider rules (Workday is excluded by project rule); onboarding more Greenhouse/Lever/Ashby boards can remove at most 17.5% of the feed's rows.

### Provider histogram of listings not DIRECT ACTIVE (1,002)

| Provider | Listings | Share of not-active |
|---|---|---|
| workday | 617 | 61.6% |
| oracle (HCM Cloud) | 149 | 14.9% |
| greenhouse, board not in catalog | 120 | 12.0% |
| ashby, not in catalog | 37 | 3.7% |
| lever, not in catalog | 19 | 1.9% |
| smartrecruiters, not in catalog | 13 | 1.3% |
| rippling | 11 | 1.1% |
| greenhouse / ashby / lever / smartrecruiters, in catalog but not enabled | 10 / 3 / 1 / 1 | 1.5% |
| amazon (amazon.jobs, in-house) | 9 | 0.9% |
| workable, not in catalog | 8 | 0.8% |
| breezy | 4 | 0.4% |

197 "supported but not configured" listings sit on about 190 distinct boards, almost all with 1 to 5 listings: a long tail, not a concentrated win. After this change's 26 additions, 44 of them are on catalog boards (153 remain unconfigured).

## Top 50 organizations by open feed listings not covered by an enabled direct source

Status key: **FEED FALLBACK** = only reachable through the feed today (unsupported provider); GREEN = supported provider, board not cataloged. Paths for Workday/Oracle assume a new adapter (outside current provider rules).

| # | Organization | Listings | Apply-URL provider (board/domain) | Status | Relevance | Potential direct path |
|---|---|---|---|---|---|---|
| 1 | Booz Allen | 67 | Workday `bah` | FEED FALLBACK | M (SWE, data/ML; cleared roles) | Workday CXS adapter |
| 2 | American Express | 33 | Oracle HCM `egug.fa.us2` | FEED FALLBACK | M (SWE, ML) | Oracle HCM adapter |
| 3 | RTX | 29 | Workday `globalhr` | FEED FALLBACK | H (flight control SW, DSP, embedded) | Workday |
| 4 | CACI | 25 | Workday `caci` | FEED FALLBACK | M (SWE, security) | Workday |
| 5 | Nokia | 21 | Oracle HCM `fa-evmr-saasfaprod1` | FEED FALLBACK | H (AI R&D co-ops, telecom) | Oracle HCM |
| 6 | General Dynamics Information Technology | 20 | Workday `gdit` | FEED FALLBACK | M | Workday |
| 7 | Stantec | 18 | Oracle HCM `hdhl.fa.us6` | FEED FALLBACK | L (civil engineering) | none worth it |
| 8 | Leidos | 18 | Workday `leidos` | FEED FALLBACK | M | Workday |
| 9 | Emerson Electric | 18 | Oracle HCM `hdjq.fa.us2` | FEED FALLBACK | H (embedded/controls SWE) | Oracle HCM |
| 10 | Gilead Sciences | 16 | Workday `gilead` | FEED FALLBACK | L (biotech data) | Workday |
| 11 | Cox | 13 | Workday `cox` | FEED FALLBACK | M | Workday |
| 12 | Johnson & Johnson | 12 | Workday `jj` | FEED FALLBACK | L | Workday |
| 13 | Amgen | 11 | Workday `amgen` | FEED FALLBACK | L | Workday |
| 14 | Motorola Solutions | 10 | Workday `motorolasolutions` | FEED FALLBACK | H (embedded, Android) | Workday |
| 15 | Wex | 10 | Workday `wexinc` | FEED FALLBACK | M | Workday |
| 16 | Amazon | 9 | `amazon.jobs` (in-house) | FEED FALLBACK (YELLOW) | H (SDE, embedded, robotics) | undocumented search XHR only; keep feed |
| 17 | GM Financial | 9 | Oracle HCM `fa-exvu` | FEED FALLBACK | M | Oracle HCM |
| 18 | Honeywell | 9 | Oracle HCM `ibqbjb` | FEED FALLBACK | H (SWE, aerospace) | Oracle HCM |
| 19 | Genuine Parts Company | 9 | Workday `genpt` | FEED FALLBACK | L | Workday |
| 20 | Micron Technology | 8 | Workday `micron` | FEED FALLBACK | H (firmware, memory arch, SSD) | Workday |
| 21 | Sierra Nevada Corporation | 8 | Workday `snc` | FEED FALLBACK | H (aerospace SWE, security) | Workday |
| 22 | Avav (AeroVironment ticker) | 8 | Workday `avav` | FEED FALLBACK | H (embedded, UAS software) | Workday |
| 23 | BNY | 8 | Oracle HCM `eofe.fa.us2` | FEED FALLBACK | M | Oracle HCM |
| 24 | Texas Instruments | 7 | Oracle HCM `edbz.fa.us2` | FEED FALLBACK | H (systems, SW, ML) | Oracle HCM |
| 25 | Intel | 7 | Workday `intel` | FEED FALLBACK (RED) | H (AI/graphics research) | Workday |
| 26 | Vanguard | 7 | Workday `vanguard` | FEED FALLBACK | L | Workday |
| 27 | Allegion | 7 | Workday `allegion` | FEED FALLBACK | M (SW, hardware) | Workday |
| 28 | Oshkosh | 7 | Workday `oshkoshcorporation` | FEED FALLBACK | M (robotics programming) | Workday |
| 29 | US Foods | 7 | Workday `usfoods` | FEED FALLBACK | L | Workday |
| 30 | The Hartford | 7 | Workday `thehartford` | FEED FALLBACK | L | Workday |
| 31 | JPMorganChase | 7 | Oracle HCM `jpmc.fa` | FEED FALLBACK | M (quant) | Oracle HCM |
| 32 | General Motors | 6 | Workday `generalmotors` | FEED FALLBACK | H (ML/AI) | Workday |
| 33 | HP | 6 | Workday `hp` | FEED FALLBACK | M | Workday |
| 34 | Cisco | 6 | Workday `cisco` | FEED FALLBACK | H (firmware, SWE co-op) | Workday |
| 35 | Moog | 6 | Workday `moog` | FEED FALLBACK | H (embedded design) | Workday |
| 36 | Q2 | 6 | Workday `q2ebanking` | FEED FALLBACK | M | Workday |
| 37 | Cencora | 6 | Workday `myhrabc` | FEED FALLBACK | L | Workday |
| 38 | Gordon Food Service | 6 | Workday `gfs` | FEED FALLBACK | L | Workday |
| 39 | Stryker | 6 | Workday `stryker` | FEED FALLBACK | M | Workday |
| 40 | The Federal Reserve System | 5 | Workday `rb` | FEED FALLBACK | L | Workday |
| 41 | Philips | 5 | Workday `philips` | FEED FALLBACK | H (embedded test, imaging SW) | Workday |
| 42 | NISC | 5 | Greenhouse `testnisc` | GREEN (not cataloged) | M | board name looks like a test board; not added |
| 43 | TD Bank | 5 | Workday `td` | FEED FALLBACK | L | Workday |
| 44 | Auto-Owners Insurance | 5 | Workday `aoins` | FEED FALLBACK | L | Workday |
| 45 | McKesson | 5 | Workday `mckesson` | FEED FALLBACK | L | Workday |
| 46 | DraftKings | 5 | Workday `draftkings` | FEED FALLBACK | M | Workday |
| 47 | Hewlett Packard Enterprise | 4 | Workday `hpe` | FEED FALLBACK | M | Workday |
| 48 | Graco | 4 | Workday `graco` | FEED FALLBACK | L | Workday |
| 49 | Bracco | 4 | Workday `bracco` | FEED FALLBACK | L (firmware co-op) | Workday |
| 50 | KLA | 4 | Workday `kla` | FEED FALLBACK | H (algorithm, SWE; semi equipment) | Workday |

Reading: 49 of the top 50 are Workday, Oracle HCM, or amazon.jobs. The only supported-provider organization (NISC, rank 42) is a likely test board; the real supported-but-unconfigured boards hold 1 to 5 listings each and are in the next section.

## Supported provider, not configured: verified new catalog boards (26)

One GET per board to the provider's documented public API on 2026-10-06 (Greenhouse `boards-api.greenhouse.io/v1/boards/{slug}/jobs`, Lever `api.lever.co/v0/postings/{slug}?mode=json`, Ashby `api.ashbyhq.com/posting-api/job-board/{slug}`), plus one GET to the careers page where reachable. Evidence class A = careers page references the board slug; B = API answers with the company's own board name and links but the careers page was JS-only/403/slug not visible. All 26 added to `backend/data/direct_source_catalog.json` (not enabled). Feed = listings currently in the community feed.

| Org | Board | Postings / interns | Feed rows | Ev. | Tags | Relevance |
|---|---|---|---|---|---|---|
| Muon Space | greenhouse:muonspace | 138 / 15 | 2 | A | aerospace, hardware | H (EE, test, applied science) |
| K2 Space | greenhouse:k2spacecorporation | 248 / 10 | 2 | A | aerospace, hardware | H (avionics, EE, dynamics) |
| General Matter | greenhouse:generalmatter | 129 / 15 | 2 | A | research, hardware | H (embedded SW, chemical, mechanical) |
| Rendezvous Robotics | greenhouse:rendezvousrobotics | 24 / 9 | 1 | B (careers 403) | robotics, aerospace, hardware | H (avionics, GNC) |
| Graphcore | greenhouse:graphcore | 178 / 5 | 1 | A | ai, semiconductor, hardware | H (firmware, hardware platform) |
| Pacific Fusion | greenhouse:pacificfusion | 27 / 5 | 1 | A | research, hardware | H (EE, controls) |
| QuEra Computing | greenhouse:queracomputinginc | 77 / 7 | 1 | A | research, hardware | H (quantum compilers, error correction) |
| Stoke Space | greenhouse:stokespacetechnologies | 65 / 3 | 1 | A | aerospace, hardware | H |
| GITAI | greenhouse:gitai | 18 / 4 | 1 | A | robotics, aerospace, hardware | M-H (software, mechanical) |
| Mill | greenhouse:mill | 31 / 8 | 1 | A (careers redirects to board) | hardware, robotics | H (EE, computer vision) |
| Hadrian | ashby:hadrian-automation | 136 / 3 | 2 | B | robotics, hardware | M-H |
| Cowboy Space | ashby:cowboyspace | 83 / 3 | 1 | A | aerospace, hardware | M-H |
| The Exploration Company | ashby:the-exploration-company | 107 / 7 | 1 | A | aerospace, hardware | H, EU-heavy |
| Harbinger Motors | greenhouse:harbingermotors | 90 / 7 | 1 | A | mobility, hardware | H (electrical distribution) |
| Bot Auto | greenhouse:botauto | 24 / 3 | 1 | A | mobility, robotics, ai | M-H |
| IMC Trading | greenhouse:imc | 170 / 18 | 4 | A | fintech, software, hardware | H (hardware/FPGA, deep learning, SWE); many roles in Amsterdam |
| Virtu Financial | greenhouse:virtu | 48 / 15 | 3 | A | fintech, software, hardware | H (FPGA, hardware engineer) |
| Hudson River Trading | greenhouse:wehrtyou | 87 / 7 | 3 | B | fintech, software | M-H (algorithm dev, SWE) |
| Tower Research Capital | greenhouse:towerresearchcapital | 93 / 12 | 2 | A | fintech, software | M (SWE, AI/ML) |
| Talos | ashby:talos-trading | 17 / 5 | 2 | A | fintech, software | M |
| Five Rings | greenhouse:fiveringsllc | 17 / 4 | 2 | A | fintech, software | M |
| TensorWave | ashby:tensorwave | 54 / 16 | 3 | A | ai, cloud | M-H (SWE, security; AMD GPU cloud) |
| Epic Games | greenhouse:epicgames | 145 / 22 | 3 | B (careers 403) | software | M (programmers, data science) |
| Tanium | greenhouse:tanium | 56 / 8 | 1 | A | cloud, software | M |
| Rubrik | greenhouse:rubrik | 131 / 5 | 0 | B (careers 403) | cloud, software | M |
| Immuta | lever:immuta (global) | 13 / 5 | 2 | A | cloud, software | M |

Totals: **26 boards, about 221 board-wide intern title matches, 44 current feed rows**. Greenhouse 20, Ashby 5, Lever 1. Notes: `greenhouse:imc` posts on `job-boards.eu.greenhouse.io` but its documented global API answers; the catalog has no Greenhouse region field. The feed's campus-specific boards (`klaviyocampus`, `formlabsinternships`, `ctccampusboard`, `walleyecapital-external-students`) are sibling boards whose company boards differ; they were not added (Klaviyo timed out, Formlabs already cataloged, the others are internship-only sidecar boards with unclear ownership of the canonical board).

### Checked and not added

| Board | Reason |
|---|---|
| ashby:northwoodspace, greenhouse:amperesand, lever:xcimer | API 200 with intern roles (9 / 5 / 6), but no official careers domain could be resolved (DNS failure or timeout), so ownership was not confirmed |
| lever:mobileye | 404 (the expansion research's earlier eu-host verification is not reproduced on the global host; unchanged) |
| greenhouse:testnisc, greenhouse:riotgamesup, greenhouse:ctccampusboard | test or sidecar boards (see note above) |
| apptronik, agility, relativity, d-matrix | API 200, zero intern titles today; stay watch-list |
| point72, schonfeld, relaypro | API 200 but mostly finance/ops/accounting interns (low relevance) |
| affirm, glean, harvey, sierra, exa, voleon, belvedere, covar, clockwork, viam, katalyst, melius | API 200 but 1 to 3 interns and lower hardware relevance; candidates for a later batch |
| greenhouse:xai | ownership/name changed ("SpaceXAI") per the expansion research |
| greenhouse:klaviyocampus | request timed out |

## Company-universe classification (51 companies)

Classes: DIRECT ACTIVE (enabled in production, approximated), DIRECT AVAILABLE (cataloged, not enabled), CATALOG VERIFIED (cataloged but not activatable today), GREEN NEW ADAPTER (supported provider, new board: none of the 51 remain), YELLOW (no documented API or unverified), FEED FALLBACK (reachable only via the feed; underlying provider named), ABSENT (nothing open), RED (excluded or forbidden). ATS evidence: provider API or careers page fetched 2026-10-06 (one request each); Workday tenants are named by the feed's ids. "0 interns" boards are DIRECT AVAILABLE but ABSENT today.

| Company | ATS (evidence) | Class | Notes |
|---|---|---|---|
| OpenAI | ashby:openai | DIRECT AVAILABLE | 0 interns (ABSENT today) |
| Anthropic | greenhouse:anthropic | DIRECT AVAILABLE | 0 interns (ABSENT today) |
| Databricks | greenhouse:databricks | DIRECT AVAILABLE | 11 interns |
| Cloudflare | greenhouse:cloudflare | DIRECT AVAILABLE | 4 |
| Stripe | greenhouse:stripe | DIRECT ACTIVE | activated 2026-10-06 |
| Snowflake | ashby:snowflake | DIRECT AVAILABLE | 5 |
| Figma | greenhouse:figma | DIRECT AVAILABLE | 8 interns; 3 feed rows |
| MongoDB | greenhouse:mongodb | DIRECT AVAILABLE | 0 interns (ABSENT today) |
| Reddit | greenhouse:reddit | DIRECT AVAILABLE | 0 interns (ABSENT today) |
| Coinbase | greenhouse:coinbase | DIRECT ACTIVE | 5 feed rows duplicate |
| Palantir | lever:palantir | DIRECT ACTIVE | |
| Scale AI | greenhouse:scaleai | DIRECT AVAILABLE | 1 feed row |
| Together AI | greenhouse:togetherai | DIRECT ACTIVE | |
| Cohere | ashby:cohere | DIRECT AVAILABLE | 3 |
| Waymo | greenhouse:waymo | DIRECT ACTIVE | 5 feed rows duplicate |
| Anduril | greenhouse:andurilindustries | CATALOG VERIFIED | 25 interns; 2,457 jobs exceed the 20 MiB response cap, disabled |
| Skydio | ashby:skydio | DIRECT ACTIVE | |
| Zipline | greenhouse:flyzipline | DIRECT ACTIVE | |
| Figure | greenhouse:figureai | DIRECT ACTIVE | slug `figure` is a different company |
| Tesla | in-house; careers 403 to a plain fetch | RED | bot-blocked |
| SpaceX | greenhouse:spacex | CATALOG VERIFIED | 12 interns; same response-size failure as Anduril |
| Rocket Lab | greenhouse:rocketlab | DIRECT ACTIVE | |
| Astranis | greenhouse:astranis | DIRECT ACTIVE | |
| Varda | greenhouse:vardaspace | DIRECT ACTIVE | |
| Impulse Space | pinpoint:impulsespace | DIRECT ACTIVE | |
| Shield AI | lever:shieldai | DIRECT AVAILABLE | 6; 1 feed row |
| Saronic | ashby:saronic | DIRECT ACTIVE | |
| Neuralink | greenhouse:neuralink | DIRECT ACTIVE | |
| NVIDIA | Workday tenant `nvidia` (feed ids); careers page is a front end | FEED FALLBACK (RED: Workday) | 2 feed rows |
| AMD | iCIMS (careers page) | YELLOW | no documented API; 0 feed rows |
| Intel | Workday `intel` (feed ids) | FEED FALLBACK (RED: Workday) | 7 feed rows |
| Qualcomm | Eightfold (careers page) | YELLOW | 0 feed rows |
| Broadcom | not re-verified (careers fetch timed out) | YELLOW | carried forward |
| Marvell | Workday `marvell` (feed ids; careers 403) | FEED FALLBACK (RED: Workday) | 4 feed rows |
| Micron | Workday `micron` (feed ids; careers page Eightfold front end) | FEED FALLBACK (RED: Workday) | 8 feed rows; the expansion note's "Eightfold" is the front end |
| Arm | iCIMS (careers page) | YELLOW | Pinpoint `arm` is an unrelated tenant |
| Texas Instruments | Oracle HCM `edbz.fa.us2` (careers page, feed ids) | FEED FALLBACK (YELLOW) | 7 feed rows |
| Analog Devices | not re-verified (timed out) | YELLOW | carried forward |
| Microchip | Workday `microchiphr` (feed id; careers 403) | FEED FALLBACK (RED: Workday) | 1 feed row |
| Applied Materials | Workday `amat` (feed id); careers page Eightfold | FEED FALLBACK (RED: Workday) | 1 feed row |
| Lam Research | Eightfold (careers page) | YELLOW | 0 feed rows |
| KLA | Workday `kla` (careers page, feed ids) | FEED FALLBACK (RED: Workday) | 4 feed rows |
| ASML | no ATS marker on careers page | YELLOW | undetermined |
| Synopsys | Avature (careers page) | YELLOW | |
| Cadence | not re-verified (careers 403) | YELLOW | carried forward |
| Amazon | in-house `amazon.jobs` | FEED FALLBACK (YELLOW) | 9 feed rows; undocumented XHR only |
| Apple | in-house | YELLOW | sitemap only |
| Google | in-house | RED | robots disallows job paths |
| Meta | in-house | RED | robots notice forbids automation |
| Microsoft | in-house / Eightfold PCSX | YELLOW | |
| Netflix | Eightfold (careers page) | YELLOW | |

No company in this list falls into GREEN NEW ADAPTER: every one with a supported-provider board is already in the catalog. Tally: DIRECT ACTIVE 14, DIRECT AVAILABLE 11 (4 of them with 0 interns today), CATALOG VERIFIED 2, FEED FALLBACK 9, YELLOW 12, RED 3.

## Ranked next activations (new boards, supported providers)

Ordered by EE/CS/hardware relevance first, then board-wide intern count. All 26 are in the catalog now; none are enabled. Activate in batches (largest-intern, highest-relevance first) and re-measure at the 50-source cap (see below).

| Rank | Board | Interns | Why |
|---|---|---|---|
| 1 | greenhouse:muonspace | 15 | EE, environmental test, applied science; satellites |
| 2 | greenhouse:generalmatter | 15 | embedded SW, chemical/mechanical; enrichment hardware |
| 3 | greenhouse:k2spacecorporation | 10 | avionics, EE, dynamics |
| 4 | greenhouse:imc | 18 | hardware/FPGA, deep learning research, SWE |
| 5 | greenhouse:virtu | 15 | FPGA and hardware engineer interns, SWE |
| 6 | greenhouse:rendezvousrobotics | 9 | avionics, GNC |
| 7 | greenhouse:mill | 8 | EE, computer vision |
| 8 | greenhouse:harbingermotors | 7 | electrical distribution, controls |
| 9 | greenhouse:queracomputinginc | 7 | quantum compiler and QEC research |
| 10 | ashby:the-exploration-company | 7 | radiation testing of electronics; EU-heavy |
| 11 | greenhouse:graphcore | 5 | firmware, hardware platform |
| 12 | greenhouse:pacificfusion | 5 | EE, controls |
| 13 | greenhouse:gitai | 4 | robotics software, mechanical |
| 14 | greenhouse:stokespacetechnologies | 3 | engineering, software |
| 15 | ashby:hadrian-automation | 3 | robotics, SWE |
| 16 | ashby:cowboyspace | 3 | launch/satellite, SWE |
| 17 | greenhouse:botauto | 3 | deep learning, AV software |
| 18 | ashby:tensorwave | 16 | SWE, security; AI cloud |
| 19 | greenhouse:epicgames | 22 | programmers, data science |
| 20 | greenhouse:wehrtyou (Hudson River Trading) | 7 | algorithm dev, SWE |
| 21 | greenhouse:towerresearchcapital | 12 | SWE, AI/ML |
| 22 | greenhouse:tanium | 8 | cloud security SWE |
| 23 | ashby:talos-trading | 5 | SWE |
| 24 | lever:immuta | 5 | platform/SRE, full-stack |
| 25 | greenhouse:rubrik | 5 | engineering interns |
| 26 | greenhouse:fiveringsllc | 4 | trading/SW |

Notes: ranks 1 to 17 are the EE/hardware/space/robotics set (about 137 interns); ranks 18 to 26 are CS-centric (about 84). IMC and Virtu are quant firms but carry real hardware/FPGA roles, so they rank with hardware.

## Estimated independent-coverage gain if all 26 were activated

Baseline from the release record: independent discovery 56.5% (1,319 of 2,335 open), feed-only 1,016. Assumptions: the 44 current feed rows on these boards become direct-backed (already counted as open, so they move from feed-only to independent); the remaining about 177 board-wide intern matches (221 minus 44) are new opportunities, kept at 50% to 100% (non-US and non-technical roles may be filtered or low value). Result: (1,319 + 44 + 88..177) / (2,335 + 88..177) = **59.9% to 61.3%, about +3.4 to +4.8 points**. Not production-measured. The first sync of a new board added 3 to 96 postings in the 2026-10-06 activation, consistent with these board sizes.

Operational note: 45 + 26 = 71 enabled direct sources would exceed the measured cap of 50 ([operations.md](../operations.md#operational-source-cap)); at most 5 more fit today without retiring boards. The coverage ceiling from adding Greenhouse/Lever/Ashby boards is small: even all 197 unconfigured supported listings are 17.5% of the feed, while 68% of the feed is Workday and Oracle HCM. Raising independence materially needs an adapter for those providers, which today requires an ADR (Workday is excluded by project rule).

## Re-running

`python backend/scripts/feed_pareto.py [TOP_N]` fetches the public feed once and prints the status, provider, top-N organization, and unconfigured-board tables as markdown. It reads no database; update its `ENABLED` set after each activation batch. The catalog-side numbers above (15 DIRECT AVAILABLE, 197 unconfigured) are from the 64-entry catalog; with the 90-entry catalog the script reports 59 and 153.
