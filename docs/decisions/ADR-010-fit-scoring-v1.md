# ADR-010: Fit Scoring v1, Match Profile, and Internships-Only ATS Scope

Status: Accepted

Date: 2026-09-29

## Context

[ADR-001](ADR-001-separate-eligibility-and-fit.md) separates eligibility (may the owner apply?) from fit (how well does the posting match?). Eligibility v1 exists; fit doesn't. The approved v1 weights are in [docs/scoring.md](../scoring.md). [ADR-006](ADR-006-core-domain-persistence-model.md) reserved nullable fit columns on `opportunity_evaluations` and deferred preferences, remote preference, and availability until scoring. [ADR-003](ADR-003-ai-as-enrichment.md) and [ADR-004](ADR-004-technology-stack.md) require v1 to work without AI, paid APIs, or new services.

Milestone 4 also has two operational problems to fix: a Greenhouse/Lever board imports every posting (mostly full-time jobs), and a profile change re-evaluates the whole catalog (~10 s for 1,055 opportunities hosted) and appends a history row for every opportunity even when nothing relevant changed.

## Decision

### 1. Eligibility first, always

Fit never changes eligibility, and eligibility never feeds fit. Ranking orders by eligibility bucket first (`eligible`, `needs_verification`, `ineligible`, then not evaluated) and by fit only inside a bucket. An ineligible opportunity with fit 100 ranks below an eligible one with fit 1.

### 2. One canonical scoring module

`backend/app/opportunities/scoring/` is pure (no database, no network, no randomness). `config.py` holds `SCORING_VERSION = "v1"`, the weights, the alias dictionary, stop words, and every numeric threshold below. Nothing else defines them; the frontend only displays what the backend stored. Changing any rule or number means `v2`; stored v1 evaluations keep their version.

### 3. Weights, scale, rounding

| Component | Key | Weight |
|---|---|---:|
| Technical match | `technical` | 35 |
| Academic match | `academic` | 20 |
| Project / research match | `projects` | 15 |
| Interest match | `interests` | 10 |
| Location / schedule match | `location_schedule` | 10 |
| Opportunity quality | `quality` | 10 |

Each component score is an integer 0–100. `fit_score = round_half_up(Σ score × weight / 100)`, computed as `(Σ + 50) // 100` on integers. Every ratio inside a component also rounds half up (`(2n + d) // 2d`), never with Python's banker's rounding.

### 4. Missing data and coverage

Unknown is never a match. A component without usable evidence scores **0** and is marked `missing`, with `missing_input` saying whether the profile (`profile`) or the posting (`opportunity`) lacked it. There is no 50 % default.

`coverage` = the sum of the weights of the components that were evaluated. Opportunity quality needs no profile data, so coverage is at least 10. A low score with low coverage means "incomplete profile", not "poor match"; the UI shows both.

### 5. Profile inputs (Match Profile)

Fit reads:

- **facts** in `profile_facts` (no parallel system): categories `skill`, `course`, `project`, `research`, `activity`, `experience`. v1 reads only facts that are `verified_by_user` or `extraction_method = manual`; unverified inferred facts (none exist yet) are ignored until a later version defines how to weight them.
- **preferences** as canonical `profiles` columns: `interests` (JSON string list), `preferred_locations` (JSON string list), `remote_preference` (`no_preference`, `remote_preferred`, `hybrid_preferred`, `onsite_preferred`, `remote_only`), `availability_start`, `availability_end` (CHECK `availability_end >= availability_start`). They are fit inputs only; eligibility doesn't read them.

The owner edits everything through one atomic `PUT /api/profile/match`. Its manual facts are stored with `source_kind = manual`, `extraction_method = manual`, `verified_by_user = true`, no `profile_source_id`, and `fact_key = "match_profile.NNN"` (position). Fact values are typed JSON: `{"name": …}` for skills and courses, `{"name": …, "description": …}` for the rest. A save replaces only rows it owns (manual + `match_profile.` key prefix + those six categories). Any other fact (parser, AI, résumé, GitHub, future) is never touched. Limits: 50 skills, 50 courses, 30 interests, 20 preferred locations, 25 each of projects/research/activities/experience; names ≤ 150 characters (skills/interests/locations ≤ 100), descriptions ≤ 2,000. Activities and experience are stored and shown but don't score in v1: no deterministic rule for them was agreed, and quietly folding them into another component would change its definition.

### 6. Deterministic text matching

`scoring/text.py` normalizes with Unicode NFKC and case folding, then tokenizes into lowercase words while keeping meaningful punctuation: `c++`, `c#`, `.net`, `node.js`. Hyphens, slashes, and other punctuation separate words (`machine-learning` = `machine learning`, `ci/cd` = `ci cd`). A term (skill, interest, course) matches when its token sequence appears **contiguously** in the posting's token sequence, or when one of its aliases does. Aliases are one small, version-controlled table (`js`/`javascript`, `ts`/`typescript`, `ml`/`machine learning`, `ai`/`artificial intelligence`, `postgres`/`postgresql`, `k8s`/`kubernetes`, `nlp`/`natural language processing`, `aws`/`amazon web services`, `react`/`reactjs`/`react.js`, `node.js`/`nodejs`, `.net`/`dotnet`, `golang`/`go lang`). No fuzzy matching, stemming, embeddings, or external libraries. Explanations list the owner's own wording of what matched.

The posting corpus is `title + description` (technical, academic, projects) or `title + organization + description` (interests).

### 7. Component rules

**Technical (35).** Usable skills = distinct non-empty normalized skills. Score = `round_half_up(100 × matched / usable)`. Breakdown: `matched`, `unmatched`. No skills → missing (profile).

**Academic (20).** Per course: **exact** (the whole course title, or an alias, appears) = 2 points; **keywords** (every informative word of the title appears somewhere, at least one such word) = 1 point; otherwise 0. Informative words exclude stop words and course filler (`intro`, `introduction`, `advanced`, `honors`, `ap`, `ib`, `fundamentals`, `principles`, `topics`, roman numerals, numbers). Score = `round_half_up(100 × points / (2 × courses))`. The hard education requirement is never used here. No courses → missing (profile).

**Projects / research (15).** Each project/research item's informative words (name + description; stop words, generic job words, and words shorter than two characters removed) are compared with the posting's words. An item's strength is `min(overlap, 5) / 5`; the component score is the strongest item's, `round_half_up(100 × min(overlap, 5) / 5)`. The breakdown lists up to three strongest items with their matching keywords. Five keywords saturating is the explicit, documented rule (no hidden similarity threshold). No items → missing (profile).

**Interests (10).** Same as technical, over `title + organization + description`. No interests → missing (profile).

**Location / schedule (10).** Two sub-scores, each 0–100 or unknown:

- *Place.* Work mode (preference × posting `remote_mode`):

  | Preference | remote | hybrid | onsite |
  |---|---:|---:|---:|
  | `remote_only` | 100 | 50 | 0 |
  | `remote_preferred` | 100 | 75 | 50 |
  | `hybrid_preferred` | 75 | 100 | 75 |
  | `onsite_preferred` | 50 | 75 | 100 |
  | `no_preference` | 100 | 100 | 100 |

  Location (only for hybrid/onsite/unknown-mode postings, and only with preferred locations and a posting location): 100 if a preferred location matches, else 0. A preferred location matches when its first comma-separated part (`San Jose` of `San Jose, CA`) or its whole text appears as a phrase in the posting's location. No geocoding. Place = the lower of the known mode and location values (a remote-only owner isn't rescued by a matching city); if only one is known, that one; neither → unknown.
- *Schedule.* Needs `availability_start` and/or `availability_end` (an open side is unbounded) and the posting's `start_date`. Both posting dates known: 100 if the posting lies wholly inside availability, 50 if it partly overlaps, 0 if it doesn't overlap. Only the start known: 50 if the start falls inside availability, 0 if not. No start date → unknown.

Component = the rounded-half-up mean of the known sub-scores. Missing when the profile has no remote preference, preferred locations, or availability (profile), or when neither sub-score could be determined (opportunity).

**Opportunity quality (10).** Posting completeness, no profile input: description ≥ 200 characters 25, application URL 20, application deadline 20, start date 15, posted date 10, requirements reviewed (`partial` or `complete`) 10. Whether a source still lists the posting is **not** part of fit (availability is a list filter; including it would write history whenever a source closes a record). Always evaluated.

### 7a. Breakdown

`score_breakdown` is JSON validated by a Pydantic schema: `{scoring_version, score, coverage, components: {key: {score, weight, missing, missing_input, reason, matched, unmatched, details}}}`. `reason` is a short deterministic sentence ("Matched 2 of 3 skills: Python, SQL."). No HTML, no generated prose.

### 8. Persistence and fingerprints

`opportunity_evaluations` gets nullable `fit_score` (CHECK 0–100), `score_breakdown` (JSON), `scoring_version`, and `fit_input_fingerprint` (SHA-256 hex, CHECK length 64); a CHECK keeps all four NULL together or set together. Rows from before Milestone 4 keep NULL fit fields. Every new evaluation carries both eligibility and fit.

`fit_input_fingerprint` hashes canonical JSON of: `SCORING_VERSION`; the fit profile input (the fact values above, in stored order, and the five preference fields); and the posting's `title`, `organization`, `description`, `location`, `remote_mode`, `application_deadline`, `start_date`, `end_date`, `posted_at`, `application_url`, and `requirements_assessment_status`. Never `updated_at`, `last_seen_at`, `fetched_at`, validators, or IDs.

Automatic evaluation appends a row only when the eligibility fingerprint (which includes the rules version) or the fit fingerprint (which includes the scoring version) differs from the latest row's. The explicit **Re-evaluate** action still always appends.

### 9. Catalog re-evaluation stays synchronous

A Match Profile save or an eligibility-relevant profile change runs **one** catalog pass in the request's transaction: load every latest fingerprint in one query, read opportunities in keyset batches of 200 with their requirements, skip unchanged pairs, and flush new rows per batch. Measured timings are in [operations.md](../operations.md). A queue or background worker is not added; if hosted timings approach the proxy limit, background re-evaluation becomes a later-milestone requirement.

### 10. ATS scope: internships only by default

`ingestion_sources.scope` is `all` or `internships_only`. Greenhouse and Lever boards default to `internships_only`; the built-in feed must be `all` (CHECK `kind <> 'community_feed' OR scope = 'all'`). Existing boards are migrated to `all`, so upgrading never silently closes their postings.

`internships_only` keeps a posting only when its **title** contains, as a whole word after normalization, `intern`, `interns`, `internship(s)`, `co-op(s)`, `co op`, `coop(s)`, `apprentice(s)`, or `apprenticeship(s)`. Descriptions are never searched (full-time postings mention internships), and `student`, `new grad`, `junior`, or `entry level` don't count. Owners who want everything choose **All postings**.

The filter runs in the shared pipeline after the adapter, before identification. `ingestion_runs.filtered_count` counts excluded items: `fetched = provider items`, `filtered = excluded by scope`, `normalized = admitted to the pipeline`. Items that failed validation have no trustworthy title and stay `invalid` (so a partial run still blocks closure).

Changing a source's scope clears its `ETag`/`Last-Modified`, so the next sync fetches a full snapshot instead of a `304`. In a complete successful `internships_only` snapshot, previously imported postings that are now filtered close through the normal closure rule (never deleted); switching back to `all` reactivates them on the next sync.

## Consequences

- One new migration (profile preferences, fit columns, source scope, filtered count). Pre-M4 evaluations stay valid.
- Scores appear after the first evaluation that runs with v1: any Match Profile save runs a catalog pass that fills them in; until then recommended order degrades to eligibility bucket then newest.
- Lexical matching misses synonyms outside the alias table and can match a word used in a different sense. The breakdown shows the evidence, so errors are visible.
- Title-only internship detection misses internships titled without those words and can't catch every edge case; **All postings** is the escape hatch.
- The synchronous pass bounds memory and skips unchanged work, but its worst case still grows with catalog size.

## Alternatives Considered

- **50 % default for missing data.** Rejected: it rewards empty profiles and hides gaps.
- **Embeddings / fuzzy matching / an LLM.** Rejected for v1 (non-deterministic or paid; ADR-003, ADR-004).
- **A separate ranking-history table.** Rejected: fit belongs to the same evaluation row as eligibility (ADR-001, ADR-006).
- **Per-chip fact endpoints.** Rejected: each edit would rescore the catalog.
- **A background queue now.** Rejected: new infrastructure; the optimized synchronous pass is fast enough at this scale.
- **Description-based internship detection.** Rejected: too many false positives.
