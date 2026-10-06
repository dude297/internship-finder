# ADR-019: Fit Scoring v2

Status: Proposed (on the feature branch `feature/m11-fit-scoring-v2`; subject to owner review)

Date: 2026-10-06

Supplements [ADR-010](ADR-010-fit-scoring-v1.md) (accepted, unchanged). ADR-001 holds: nothing here reads or writes eligibility.

## Context

An audit of v1 on a 58-posting synthetic benchmark (one fictional EE/CS profile, labels 0-3 written by the author, [test data](../../backend/tests/fit_benchmark_v2.py)) found:

1. **Tokenizer-split false evidence.** Hyphens and other punctuation separate words, so `go-to-market`, `go-getter`, `C-suite`, and `rust-proof` match the skills Go, C, and Rust. 6 of 8 trap postings got false skill evidence.
2. **Missed true matches.** No alias for SystemVerilog, `printed circuit board layout` vs `PCB design`, `python3`, or deep learning vs Machine Learning; courses such as Digital Logic Design never connected to RTL/FPGA/ASIC postings. 7 of 15 strong postings ranked outside the top 20.
3. **Location is plain text.** "Bay Area" did not match Sunnyvale, and `Remote - US` with an unknown remote mode scored as an unmatched place.

## Decision

`SCORING_VERSION = "v2"`. Weights stay 35/20/15/10/10/10; no new component, no input field, no schema or frontend change. Four rule changes, all deterministic, all in `scoring/config.py` tables:

- **A. Ambiguous-skill guard.** The skills `go`, `c`, `r`, `rust` (single-word, after alias expansion) match only when (a) a programming-context word (list in config, e.g. `python`, `backend`, `grpc`, `libraries`; broad words like `skills`, `tools`, `analysis`, `statistics`, `language`, `stack`, `tech` are excluded) is within 6 words, own position excluded; (b) the two preceding words are an "experience/knowledge/proficiency/..." noun plus "with/in/of/using"; or (c) it is a bare item of a delimited list next to a known technology (`TECH_TOKENS`); and never when the previous word is in that skill's prior-word denylist (`series c`, `objective-c`, `vitamin c`, `we go`) or the next word is in its denylist (`go to/getter/with/on/...`, `c suite/level/...`, `rust proof/resistant/...`, `r d` for R&D). `go` is also in the `golang` alias group. Broad words (`software`, `systems`, `services`, `experience`, `knowledge`) are not context words. Applies to the technical component only; matching is still case-folded; the per-skill check is memoised per posting.
- **B. Reviewed aliases (two-way):** `pcb`/`printed circuit board(s)`/`pcb design`/`pcb layout`/`printed circuit board layout|design`; `python`/`python3`; `c++`/`cpp`; `verilog`/`systemverilog`/`system verilog`. **One-way related (skills only):** Machine Learning and Artificial Intelligence, looked up through any alias (`ML`, `AI`), are also credited by `deep learning`, `neural network(s)`. Related matches are labelled "related", not "alias".
- **C. Course subject groups.** Five groups with specific posting terms only (no `software`, `systems`, `models`, `control`, `hardware`, `chip`) (digital logic and architecture; circuits; signals and control; data structures and algorithms; linear algebra, machine learning, statistics). A course named in a group earns the existing keyword point (1) when any of the group's posting terms appears and the course did not match by name or words. The breakdown names the posting term (`details.groups`).
- **D. Locations.** A region table (Bay Area cities). A preferred location that is a region label (`Bay Area`, `Silicon Valley`) scores 100 against any listed city; a preferred city scores 75 against another city of the same region; exact matches still score 100. The remainder of the posting location may hold only CA/US words, `SF`/`Greater`, and a ZIP code, so other states and countries never region-match (an exact city text match such as `San Jose, Costa Rica` for a `San Jose, CA` preference is the unchanged v1 rule). If `remote_mode` is unknown and the location text is exactly "Remote" optionally followed by the US or one US state, the posting is treated as remote (a known mode is never overridden; `Remote - Canada` and `Not remote` are not). This is fit scoring only; eligibility does not import or see it.

Every contribution is explained: skill reasons say `Verilog (alias systemverilog)` / `Machine Learning (related deep learning)` with `details.evidence`; the academic reason says `course group: Digital Logic Design (posting says asic)`; the location reason says `Region match: "Sunnyvale, CA" is in the bay area region.` or `Location text says remote...`.

Freshness as final tie-breaker already exists (`discovery._order` ends every sort with newest posted date, then first seen, then ID), so nothing changes there, and nothing time-related enters `score_fit` or the fingerprint.

### Deferred

Role-family component (biggest measured gain but needs weights and frontend changes), activities and experience into projects (no measured benefit), deadline urgency (UI only).

## Measurements

Synthetic, author-labelled, so a regression and direction check, not a generalisation estimate. Same 58 postings; NDCG@10 over labels 0-3.

| Profile | | v1 | v2 |
|---|---|---:|---:|
| EE/CS (drove the rules) | NDCG@10 | 0.826 | 0.865 |
| | precision@10 (label >= 2) | 0.90 | 1.00 |
| | strong postings outside top 20 | 7 | 3 |
| | trap postings with false Go/C/Rust evidence | 6 of 8 | 0 |
| Software-only (overfitting check) | NDCG@10 | 0.708 | 0.762 |
| | precision@10 (label >= 2) | 0.60 | 0.70 |
| | trap postings with false Go/C/Rust evidence | 5 | 0 |

Enforced by `backend/tests/test_fit_benchmark.py` (EE NDCG >= 0.84, the measured 0.865 minus a small margin, traps 0, strong outside top 20 <= 3; software-only not worse than v1 by more than 0.03).

## Consequences

- v1 evaluation rows are never rewritten (ADR-006). Review fixes (R&D, list recall, generic context and group words) lowered the EE/CS NDCG@10 from the prototype's 0.892 to 0.865 and raised the software-only one from 0.736 to 0.762. `SCORING_VERSION` is in the fit fingerprint, so every opportunity is stale: after deploying, run `python -m app.cli reevaluate --dry-run`, then `reevaluate` ([ADR-018](ADR-018-evaluation-staleness.md), [deployment.md](../deployment.md#release-procedure)). It appends one v2 row per opportunity (~1 row each); lists switch to v2 as the latest row wins. Until `reevaluate` finishes, a list orders a mix of v1 and v2 scores (same weights, different evidence rules), so run it immediately after the deploy. v1 and v2 scores of one posting are comparable (same weights) but not equal.
- Recall risk of the guard: a bare short mention with no context word (a lone "Go") and phrases such as "Go with ..." / "Go on ..." are rejected. The tables need review as new traps and misses appear.
- Related and region tables are judgment calls and cover only what is listed.
