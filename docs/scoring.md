# Fit Scoring

Scoring is **versioned behavior**. Status: **v1 in production** (Milestone 4, [ADR-010](decisions/ADR-010-fit-scoring-v1.md)); **v2 implemented on the development branch, not released** (Milestone 11, [ADR-019](decisions/ADR-019-fit-scoring-v2.md)). The component table and weights below apply to both; [v2 changes](#v2-changes-adr-019) lists what differs.

## Principles

- **Fit is not eligibility** ([ADR-001](decisions/ADR-001-separate-eligibility-and-fit.md)). Eligibility asks "may I apply?"; fit asks "how well does this posting match me?". Fit never reads or changes an eligibility result, and eligibility never reads fit.
- **Eligibility first.** The recommended order is eligibility bucket first (`eligible`, `needs_verification`, `ineligible`, then not evaluated) and fit only inside a bucket. An ineligible posting with fit 100 ranks below an eligible posting with fit 1.
- **One canonical location.** `backend/app/opportunities/scoring/config.py` holds `SCORING_VERSION`, the weights, the alias dictionary, stop words, and every threshold. The backend is authoritative; the frontend only displays stored results.
- **Deterministic.** No AI, embeddings, randomness, network, or paid service ([ADR-003](decisions/ADR-003-ai-as-enrichment.md), [ADR-004](decisions/ADR-004-technology-stack.md)). Same inputs, same score.
- **Unknown is never a match.** A component without evidence scores 0 and is marked missing; coverage shows how much of the score could be measured.
- **Provenance.** v1 reads only facts with `review_state = accepted`: Match Profile entries, and imported facts after the owner accepts them on the Imported Profile page ([ADR-011](decisions/ADR-011-profile-source-ingestion-and-review.md)). Pending and rejected imported facts never score ([ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md)). Accepting imported facts changes the fit input, so the batch triggers one catalog pass; the scoring rules and version stay `v1`.

## Inputs

**Match Profile** (`GET`/`PUT /api/profile/match`, the Profile → Match Profile page):

| Input | Stored as | Scores in |
|---|---|---|
| Skills | `profile_facts` (`skill`, accepted) | Technical |
| Courses | `profile_facts` (`course`) | Academic |
| Projects, research | `profile_facts` (`project`, `research`) | Projects / research |
| Activities, experience | `profile_facts` (`activity`, `experience`) | Shown only (not scored in v1) |
| Interests | `profiles.interests` | Interests |
| Preferred locations, remote preference, availability | `profiles` columns | Location / schedule |

**Posting:** title, organization, description, location, remote mode, application deadline, start and end dates, posted date, application URL, requirements-assessment status.

## v1 Components

Each component scores an integer 0–100. `fit = round_half_up(Σ score × weight / 100)`, computed in integers; every ratio also rounds half up (never Python's banker's rounding).

| Component | Weight | Rule | Missing when |
|---|---:|---|---|
| Technical | 35 | `100 × matched / usable` skills; a skill matches when its words (or an alias) appear contiguously in title + description | no skills |
| Academic | 20 | per course: title (or alias) appears = 2 points; every informative word of the title appears = 1 point; `100 × points / (2 × courses)` | no courses |
| Projects / research | 15 | strongest item's shared informative keywords with title + description, `100 × min(shared, 5) / 5` | no projects or research |
| Interests | 10 | `100 × matched / usable` over title + organization + description | no interests |
| Location / schedule | 10 | mean of the known *place* and *schedule* sub-scores (below) | no preference, locations, or availability (profile); neither sub-score known (posting) |
| Opportunity quality | 10 | description ≥ 200 characters 25, application URL 20, deadline 20, start date 15, posted date 10, requirements reviewed (`partial`/`complete`) 10 | never |

**Place** = the lower of the known values of:

- work mode (preference × posting mode):

  | Preference | remote | hybrid | onsite |
  |---|---:|---:|---:|
  | Remote only | 100 | 50 | 0 |
  | Prefer remote | 100 | 75 | 50 |
  | Prefer hybrid | 75 | 100 | 75 |
  | Prefer on-site | 50 | 75 | 100 |
  | No preference | 100 | 100 | 100 |

- location (not for remote postings): 100 if a preferred location's first comma-separated part or whole text appears as a phrase in the posting location, else 0. No geocoding.

**Schedule** (needs availability and the posting's start date): wholly inside availability 100, partial overlap 50, no overlap 0; start date only: 50 if it falls inside availability, else 0. No start date → unknown.

### Text matching

Unicode NFKC, case folding, and a tokenizer that keeps `c++`, `c#`, `.net`, and `node.js` while treating hyphens, slashes, and other punctuation as word breaks. Phrases match contiguously and never across fields. Aliases (one small table): `js`/`javascript`, `ts`/`typescript`, `ml`/`machine learning`, `ai`/`artificial intelligence`, `postgres`/`postgresql`, `k8s`/`kubernetes`, `nlp`/`natural language processing`, `aws`/`amazon web services`, `react`/`reactjs`/`react.js`, `node.js`/`nodejs`, `.net`/`dotnet`, `golang`/`go lang`. Informative words drop English stop words, generic job words (projects), and course filler such as `intro`, `advanced`, `ap`, and roman numerals (courses).

## v2 Changes (ADR-019)

`SCORING_VERSION = "v2"`. Weights and components are unchanged; four evidence rules change, each explained in the breakdown:

- **Ambiguous skills (technical only).** `go`, `c`, `r`, `rust` match only when (a) a programming-context word (`python`, `backend`, `grpc`, `libraries`, `skills`, `tools`, `stack`, `analysis`, `statistics`, ...) is within 6 words (the skill's own position excluded), or (b) the two words before it are "experience/knowledge/proficiency/familiarity/expertise/skills" plus "with/in/of/using", or (c) it is one bare item of a comma/slash/bullet/"or"/"and" list next to a known technology (`Tools: R, Tableau, Excel`; `- Go` / `- Terraform`), and never when the next word is in the skill's denylist (`go to`, `go getter`, `go with`, `go on`, `c suite`, `c level`, `rust proof`, `rust resistant`, `r d` for R&D, ...). `go-to-market`, `C-suite`, `R&D`, `Series C software startup`, and `rust-proof` no longer count; `We use Go and gRPC`, `Proficiency in C`, and `Tech stack: Go, AWS` do. `go` is also in the `golang` alias group; bare `go` stays behind this guard.
- **Reviewed aliases (two-way, all components):** `pcb` / `printed circuit board(s)` / `pcb design` / `pcb layout` / `printed circuit board layout|design`; `python` / `python3`; `c++` / `cpp`; `verilog` / `systemverilog` / `system verilog`. **Related (one-way, skills only):** Machine Learning is also credited by `deep learning` and `neural network(s)`. The reason reads `Verilog (alias systemverilog)` or `Machine Learning (related deep learning)`, and `details.evidence` maps skill to the evidence.
- **Course subject groups (academic).** A course in a group (digital logic / computer architecture; circuits / electronics; signals / control; data structures and algorithms; linear algebra / machine learning / statistics) earns the keyword point (1) when a specific term of its group (`rtl`, `fpga`, `asic`, `signal processing`, `algorithms`, `deep learning`, ...; never generic words such as `software`, `systems`, `models`) appears in the posting and it didn't match by name or words. The reason reads `course group: Digital Logic Design (posting says asic)`; `details.groups` maps course to term.
- **Locations (place).** Region table (Bay Area cities in `config.REGION_CITIES`): a preference of `Bay Area` or `Silicon Valley` scores 100 against any listed city; a preferred city scores 75 against another city of its region; otherwise unchanged. The rest of the posting location may only be `CA`/California/US words, so `San Jose, Costa Rica`, `Oakland, NY`, and `Fremont, NE` never region-match; the reason quotes the posting's location. If the posting's remote mode is unknown and its location text is exactly `Remote`, optionally followed by the US or one US state (`Remote - US`, `Remote (CA)`, `Remote, United States`), it is treated as remote; `Remote - Canada`, `Not remote`, and `Remote first, office in Boston` are not. A known mode is never overridden. This lives only in fit scoring; eligibility never sees it.

On a small synthetic benchmark whose postings and relevance labels the author wrote ([test](../backend/tests/test_fit_benchmark.py); an indication, not a generalisation estimate): EE/CS profile NDCG@10 0.826 to 0.865, false Go/C/Rust evidence on trap postings 6 of 8 to 0; a second software-only profile NDCG@10 0.708 to 0.762. Release: run `reevaluate` immediately after deploy; until it finishes, lists mix v1 and v2 scores ([deployment.md](deployment.md#release-procedure)).

## Coverage and Breakdown

`coverage` = the sum of the weights of evaluated components (at least 10, since quality needs no profile). A 30 with coverage 100 is a poor match; a 30 with coverage 25 mostly means the Match Profile is empty.

Each evaluation stores `score_breakdown` (JSON, validated by `ScoreBreakdown`):

```json
{
  "scoring_version": "v2",
  "score": 74,
  "coverage": 90,
  "components": {
    "technical": {
      "score": 67, "weight": 35, "missing": false, "missing_input": null,
      "reason": "Matched 2 of 3 skills: Python, SQL.",
      "matched": ["Python", "SQL"], "unmatched": ["Rust"], "details": null
    }
  }
}
```

`missing_input` is `profile` or `opportunity` for a missing component. List responses carry `fit_score`, `scoring_version`, `fit_coverage`, and per-component `{score, weight, missing}`; detail carries the full breakdown ("Why this match?").

## When Scores Change

Evaluations are history ([ADR-006](decisions/ADR-006-core-domain-persistence-model.md)): every new row carries eligibility and fit. Automatic evaluation appends a row only when the eligibility fingerprint or the fit fingerprint differs from the latest row's. The fit fingerprint hashes `SCORING_VERSION`, the fit profile inputs, and the posting fields above, never timestamps such as `updated_at`/`last_seen_at` or IDs. So:

- a Match Profile save runs one catalog pass and rescores only opportunities whose inputs changed (none when nothing changed; activities and experience don't score);
- a posting edit or sync update rescores that posting only if a fit or eligibility input changed;
- a sync that only refreshes `last_seen_at`/validators appends nothing;
- **Re-evaluate** on an opportunity always appends a row.

Evaluations from before v1 have NULL fit fields; the first catalog pass after the upgrade (any Match Profile save) fills them in. Until then, the recommended order falls back to eligibility bucket, then newest.

## Known Limitations

- Lexical only: synonyms outside the alias and related tables don't match. In v2 the guard (above) rejects ordinary-word uses of `Go`, `C`, `R`, and `Rust`, at the cost of recall: a bare mention with no programming-context word, or "Go with ..." / "Go on ...", is not credited. The tables need review as new traps and misses appear.
- A lexically true but domain-wrong match survives (a marketing posting that mentions "machine learning"); only a role signal would fix it (deferred, ADR-019).
- Location matching is plain text plus the Bay Area region table: other metros have no region, and there is no geocoding. Remote is inferred only from location text starting with "Remote".
- Activities and experience don't score.
- Scores reflect the posting text the sources provide; short or truncated descriptions match less.

## Version History

| Version | Status | Date | Notes |
|---|---|---|---|
| v1 | Implemented, in production | 2026-09-29 | Weights 35/20/15/10/10/10, rules above ([ADR-010](decisions/ADR-010-fit-scoring-v1.md)). |
| v2 | Implemented, unreleased | 2026-10-06 | Same weights; ambiguous-skill guard, reviewed aliases, course subject groups, location regions and remote-from-text ([ADR-019](decisions/ADR-019-fit-scoring-v2.md)). Release runs `reevaluate` immediately after deploy (ordering mixes v1 and v2 until it finishes). |

## Maintenance

Any change to a weight, rule, threshold, alias, or stop word bumps `SCORING_VERSION` and updates this file and an ADR (ADR-010 for v1, [ADR-019](decisions/ADR-019-fit-scoring-v2.md) for v2). Stored evaluations keep their version, so results stay comparable.
