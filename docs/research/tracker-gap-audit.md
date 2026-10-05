# Tracker Gap Audit

> **Research only (non-normative).** Date: 2026-10-05. Last verified: 2026-10-05.
> Used by / superseded by: [ADR-015](../decisions/ADR-015-freshness-requirements-v2-and-independent-discovery.md) (items 1-4 of the table adopted in Milestone 8.1); the remaining items not yet acted on.

Date: 2026-10-05. Public repo: ideas and counts only.

**No tracker data or code was imported.** Trackers were read as feature references only (READMEs and the GitHub license API). No listing data from any tracker was copied, and no tracker was used as evidence for any company or source claim (see `direct-company-source-matrix.md`). Per ADR-005, aggregated data of unclear license stays excluded; the only tracker data already consumed is the MIT-licensed zshah101 feed, as an enrichment/discovery source.

## Trackers studied

Counts are approximate (README summaries). Licenses from the GitHub API on 2026-10-05; "none detected" means the API returned null, not that the license is proven absent.

| Tracker | License | Method | Cadence | Features worth noting |
|---|---|---|---|---|
| Emjumaev/FAANG-2027-Internships-Tracker | none detected (reference only) | Scrapes company career APIs via GitHub Actions; flags ByteDance and Tesla as needing a headless browser | every 2 h | NEW marker for items added in the last 7 days; role categories; ~37 companies, ~426 open |
| zshah101 Summer/Fall Tech Internships | MIT | Polls ATS boards for ~4,700 employers | every 30 min | Posted vs first_seen; skills; citizenship/clearance, sponsorship and H-1B flags; salary; stated-cycle vs unknown-cycle; dashboard, email digest, RSS, JSON API, CSV |
| SimplifyJobs/Summer2027-Internships | none detected (check before any reuse) | Community PRs/issues plus Simplify tooling | "updated daily" | Emoji legend (closed, no sponsorship, US citizenship, advanced degree); closed rows moved to an Inactive file; hardware section |
| speedyapply/2026-SWE-College-Jobs | none detected | Curated/scraped (commercial product behind it) | daily; last 120 days only | Salary tiers; FAANG+/Quant/Other tiers; recency cutoff |
| vanshb03/Summer2027-Internships | MIT | Manual via issues/PRs | ad hoc | Posted date; closed rows stay visible with a lock; off-season split |

Pattern: closure is manual (a PR flips a lock) or "disappeared from ATS snapshot". None of the serious trackers ping URLs. Licenses for Emjumaev, Simplify and speedyapply are unverified.

## Feature gap ranking

Constraints applied: private single-user app, deterministic, official-source-first, $0, no email/push.

| # | Priority | Feature | Status |
|---|---|---|---|
| 1 | HIGH | Source freshness labels (per-source last success) | Adopted in M8.1 |
| 2 | HIGH | NEW within 7 days from our first_seen_at | Adopted in M8.1 |
| 3 | HIGH | First-seen vs provider-posted shown separately (never conflated) | Adopted in M8.1 |
| 4 | HIGH | Recently discovered sort | Adopted in M8.1 |
| 5 | HIGH | New since last visit (store last-visit timestamp, badge newer first_seen_at) | Recommended next; replaces push/email |
| 6 | HIGH | Recently closed = "provider no longer lists" after N consecutive successful, sane-sized fetches | Recommended next; no HTTP pings; label it that way, not "verified closed" |
| 7 | MEDIUM-HIGH | Company watchlist (in-app only, surfaced in new-since-last-visit) | Recommended next; design as saved filter plus badge |
| 8 | MEDIUM | Sponsorship/citizenship chips | Hint only, "verify on posting"; never hard eligibility |
| 9 | MEDIUM | Category tabs (SWE, hardware/EE, robotics, AI/ML, quant) | Saved filters; label as inferred (our classifier) |
| 10 | MEDIUM | Company pages (open, history, closed) | Pairs with watchlist |
| 11 | MEDIUM | Drop radar / expected soon | Only as a clearly labeled curated estimate ("typically opens ~Aug-Sep, curated, not verified"); never a date field, never ranked above verified postings; cap at ~30 target companies |
| 12 | LOW | Salary column | Sparse; skip |
| 13 | LOW | Skill chips | Enrichment only (ADR-003) |
| 14 | LOW | H-1B history badge | Marginal for a US student |

## Rejected ideas

| Idea | Reason |
|---|---|
| Email digest / RSS / push | No infra, $0, single user |
| Crowdsourced PR/issue curation, Inactive-README workflows | Manual, off-architecture |
| Headless-browser scraping of bot-protected sites (ByteDance/Tesla pattern) | Fragile; violates official-source-first |
| Ingesting any other tracker's listing data | License ambiguity (ADR-005) |

## Live-link validation conclusion

Basis: known ATS behavior and trackers' practices; not re-tested live in this lane (measure before relying on any claim).

| Problem | Effect |
|---|---|
| Workday and Ashby are JS shells | Closed jobs often return 200 or a redirect; status code cannot distinguish |
| Greenhouse/Lever removed jobs | Inconsistent page status; API by id returns 404 but equals what our snapshot already shows |
| Custom/iCIMS/Taleo/SuccessFactors/Eightfold | Soft-404s, redirects, cookie walls |
| Bot management on datacenter IPs | False 403/429/5xx read as "closed" |
| Volume | ~1,000 URLs x 2/day = ~2,000 requests/day on few hundred hosts: bot-score risk for little signal |

Conclusion:

- **No scheduled HEAD/GET pings.**
- Provider snapshot beats HTTP ping: absent from N consecutive successful, sane-sized fetches means "provider no longer lists". Feed-only items show "link unchecked".
- At most a later user-triggered, advisory "Check link" for a few saved items: prefer provider-API-by-id (Greenhouse/Lever); treat 403/429/5xx/redirect-to-generic as "unknown", never "closed"; 1 request per host per second, honest user agent, short timeout, one retry; result does not change stored status.

## Extra-company universe (S8, 30 names) and S9 verification

S8 names were relevance-based with ATS unverified. S9 verified each against official evidence and the documented provider API (lead counts: board postings / internship titles). "Cataloged" = in the Direct Source Catalog.

| Company | S9 outcome | Board postings / interns | Cataloged |
|---|---|---|---|
| Tesla | REJECT_AUTOMATION (site 403) | - | No |
| SpaceX | Greenhouse `spacex` | 2645 / 15 | Yes |
| Anduril | Greenhouse `andurilindustries` | 2442 / 20 | Yes |
| Boston Dynamics | Workday, feed fallback | - | No |
| Skydio | Ashby `skydio` | 144 / 8 | Yes |
| Nuro | Greenhouse `nuro` | 102 / 2 | Yes |
| Aurora Innovation | Platform not identified, feed fallback | - | No |
| Zoox | Lever `zoox` | 234 / 0 | Yes |
| Rivian | iCIMS, feed fallback | - | No |
| Lucid | Greenhouse `lucidmotors` | 437 / 0 | Yes |
| Western Digital | SmartRecruiters `westerndigital` | 318 / 4 | Yes |
| Seagate | SuccessFactors, feed fallback | - | No |
| NXP | Workday, feed fallback | - | No |
| Skyworks | SuccessFactors, feed fallback | - | No |
| Qorvo | Platform unverified (429), feed fallback | - | No |
| GlobalFoundries | Workday, feed fallback | - | No |
| Samsung Semiconductor US | Workday, feed fallback | - | No |
| SK hynix America | Unverified (unreachable), feed fallback | - | No |
| Lockheed Martin | Eightfold, feed fallback | - | No |
| Northrop Grumman | Eightfold, feed fallback | - | No |
| RTX | Phenom, feed fallback | - | No |
| Intuitive Surgical | SmartRecruiters `intuitive` | 746 / 0 | Yes |
| Cerebras | Ashby `cerebras` | 117 / 0 | Yes |
| SambaNova | Greenhouse `sambanovasystems` | 63 / 0 | Yes |
| Groq | Gem (weak evidence: search only), feed fallback | - | No |
| Tenstorrent | Greenhouse `tenstorrent` | 129 / 0 | Yes |
| SiFive | Workday, feed fallback | - | No |
| Palantir | Lever `palantir` | 319 / 45 | Yes |
| Citadel / Citadel Securities | REJECT_AUTOMATION (403) | - | No |
| Hudson River Trading | Only a talent-community board; no complete official board | - | No |

Totals: 12 of 30 cataloged, 16 feed fallback or unverified (including Hudson River Trading), 2 REJECT_AUTOMATION (Tesla, Citadel). Omitted from S8 as less relevant: Two Sigma, Jump Trading, Roblox, ByteDance/TikTok (bot-protected). Defense names often require US citizenship or clearance.
