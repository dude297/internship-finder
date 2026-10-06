# Catalog freshness audit (production, read-only)

> **Research only (non-normative).** Date: 2026-10-05. Last verified: 2026-10-05.
> Used by / superseded by: [ADR-015](../decisions/ADR-015-freshness-requirements-v2-and-independent-discovery.md) (derived freshness, Independent Discovery Coverage, empty-snapshot guard), implemented in Milestone 8.1.

Date: 2026-10-05, ~09:00–09:20 UTC. Neon production (`a8c3e5f7b9d1`, Milestone 8), queried in `READ ONLY` transactions; aggregates only, no titles or payloads. The last sync before the audit was the Milestone 8 activation dispatch at 06:14 UTC ([run 37271407847](https://github.com/dude297/internship-finder/actions/runs/37271407847)); no scheduled run happened between it and the audit. Freshness states were computed with the Milestone 8.1 code (`derive_freshness`, [ADR-015 §1](../decisions/ADR-015-freshness-requirements-v2-and-independent-discovery.md)) against production rows, read-only.

## Production health snapshot (Phase 0)

| Check | Result |
|---|---|
| Last scheduled-type run | activation dispatch 06:14 UTC, 28 sources, 0 failed, **223.7 s** |
| Failed sources | 0 |
| Partial sources | 1: `smartrecruiters:boschgroup` (detail backlog) |
| Bosch backlog | shrinking: 291 deferred items (05:03 run) → 191 (06:15 run), ~100 per run as designed (ADR-014 §2 detail budget). 200 Bosch postings active, all with descriptions. Expect healthy after ~2 more runs. |
| Bosch Source Health | `failing` (partial with no completed success yet; existing derivation) |
| Unexpected closures (48 h) | only the feed: 21 closed, 2 reactivated (normal churn) |
| Identity conflicts (since 2026-10-04) | 0 (the only run errors are 200 `detail_deferred`, i.e. Bosch's backlog) |
| Source health distribution | 27 healthy, 1 failing (Bosch) |

## Freshness state distribution (all 1,724 opportunities)

| State | Count |
|---|---|
| `direct_verified` | 416 |
| `feed_current` | 1,000 (997 feed-only + 3 Bosch postings also in the feed) |
| `source_warning` | 197 (Bosch postings: the source has never completed a full snapshot) |
| `program_listed` | 13 |
| `closed` | 98 |

## Staleness questions

| Question | Answer |
|---|---|
| Open opportunities whose best source hasn't succeeded for > 24 h / > 36 h / > 72 h | **0 / 0 / 0** (best evidence age 3.0–3.1 h at audit time). 197 have *never* had a successful source snapshot (Bosch). |
| Open opportunities whose records weren't seen in a fetched snapshot for > 24 h | 0 |
| Feed-only opportunities first seen > 30 days ago | 0 (production's catalog is 7 days old: first seen 2026-09-29 → 962, 10-02 → 137, 10-04 → 211, 10-05 → 315) |
| Feed-only opportunities **posted** > 30 days ago | 320 (24 posted > 90 days ago) |
| Direct-ATS opportunities posted > 30 days ago but still explicitly listed | 195 (35 > 90 days) — the boards still list them, so they're open by evidence; old postings are common for rolling internship programs |
| Open opportunities with no posted date | 171 (158 feed-only, 13 registry; every direct-ATS posting has one) |
| Open feed-only application URLs on unsupported provider classes | **777** of 997 by the coverage metric (feed IDs). By application URL host: Workday 593, Oracle 147, other/custom 26, Rippling 11, Breezy 4; plus Workable 8 (supported from M8.1) and Greenhouse 127 / Ashby 41 / Lever 20 / SmartRecruiters 20 (supported providers, boards not configured) |

Posted-date distribution of open postings: 1,017 in September 2026, 248 August, 97 October, 102 earlier in 2026 or before (oldest 2020-02), 171 none.

## Coverage

| Metric | Value |
|---|---|
| Open | 1,626 |
| Direct ATS | 616 |
| Curated registry | 13 |
| First-party | 0 |
| Manual only | 0 |
| Feed-only | 997 |
| **Independent Discovery Coverage** | **629 / 1,626 = 38.7%** |
| Description coverage | 629 / 1,626 = 38.7% (every independent opportunity has a description; no feed-only one does) |
| Direct-source freshness | 416 of 616 direct-backed are `direct_verified` (the rest are Bosch) |

## "New" right now

Because the production catalog is one week old, every open opportunity was first seen within 7 days at audit time (508 direct-ATS postings were first seen during the 2026-10-05 activation). The New badge becomes meaningful after the first week; until then the posted date beside it is the better age signal. The same happens for a week after any board activation.

## Conclusions

1. Twice-daily sync keeps evidence fresh: no open posting's best evidence was older than one sync interval. Freshness labels mainly separate *direct* from *feed* evidence and flag partial sources (Bosch).
2. The feed is the weak point: 997 postings with no description, no direct closure proof, and 777 on platforms the app can't read directly. Live-link pings are not the fix ([ADR-015 §3](../decisions/ADR-015-freshness-requirements-v2-and-independent-discovery.md)); direct boards are.
3. The feed barely covers the large employers the owner targets ([company matrix](direct-company-source-matrix.md)); the Direct Source Catalog is the coverage lever.
