# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

- Direct Source Catalog: 28 verified boards (36 → 64), student-relevant aerospace, robotics, AI-hardware, semiconductor, quantum, and energy employers (e.g. Rocket Lab, Zipline, Astranis, Neuralink, Etched, Quantinuum, Shield AI, Saronic), each re-verified against its provider's documented API on 2026-10-06; nothing is activated ([research](docs/research/direct-source-expansion-2026-10-06.md)).
- Milestone 8.2 (true feed independence, [ADR-016](docs/decisions/ADR-016-source-retirement-and-feed-free-bootstrap.md)): `python -m app.cli retire-source SOURCE [--apply]` closes a source's records through the pipeline's normal closure and fallback path, then disables it (dry run by default, atomic, idempotent); `bootstrap-sources` sets up a new installation from the Direct Source Catalog without the community feed (cap 50, never syncs unless `--sync`). The pipeline's closure is extracted into `close_records`, unchanged. No migration.
- Milestone 9 (in development): owner decisions on opportunities ([ADR-017](docs/decisions/ADR-017-owner-opportunity-decisions.md)). Migration `d4f8a1c6e2b9` (two nullable columns).
  - **Hide / Unhide** an opportunity (`PUT`/`DELETE /api/opportunities/{id}/dismissal`): durable across syncs (source records keep updating; never re-imported as new), excluded from the default list and the recommended sort; a **Hidden** filter (`hidden=include|only`) shows them.
  - **Revert to source** (`POST /api/opportunities/{id}/revert-to-source`) for curated imported opportunities: after confirmation, discards edits and recorded requirements and restores the authoritative active source's content, then re-evaluates; refused for manual-only opportunities.
- Curated Program Registry: 11 programs for the 2027 cycle usable by a high-school senior or incoming first-year (NIH SIP, Navy SEAP, NIST SHIP, Microsoft Discovery, Jane Street WiSE, CRA-WP DREU, Google Summer of Code, NASA Space Apps, BNL User Facility Summer School, NSF REU sites directory, FIRST volunteering); verified dates only where the official page prints them, otherwise typical windows with `verify_by` ([research](docs/research/curated-program-expansion-2027.md)).
- Evaluation staleness ([ADR-018](docs/decisions/ADR-018-evaluation-staleness.md)): `python -m app.cli reevaluate [--stale-only] [--dry-run] [--batch-size N]` (a release step after a rules/scoring version bump) and tests that both version bumps re-evaluate every opportunity. Time-triggered re-evaluation is unnecessary (rules never read today). No fingerprint change, no migration. Research: [work-authorization eligibility design](docs/research/work-authorization-eligibility-design.md) (design only).

### Changed

- Frontend responses send a strict Content-Security-Policy and a Permissions-Policy (security review L3); verified against the production build with zero violations. Takes effect on the next Vercel deploy.
- Security hardening from the 2026-10-06 review: the requirement extractor collapses horizontal whitespace runs before sentence splitting (a 50,000-space description took ~140 s, now milliseconds); CLI logs never print tracebacks or exception messages, and the database engine hides bound parameters, so public Actions logs can't carry the database host or profile-derived values; CI actions pinned to commit SHAs.
- Backend dependency lock: `backend/requirements.lock` and `backend/requirements-dev.lock` (transitive, SHA-256 hashed, universal for Python 3.12, generated with `uv pip compile`). CI, the E2E job, and the scheduled production sync install from them; Render's build command switch is an owner action ([development.md](docs/development.md#dependency-lock)). No product change.
- Documentation governance: [document authority map](docs/README.md), immutable [release records](docs/releases/) (history moved out of PROJECT_STATE.md, deployment.md, and operations.md), `docs/status.json` with generated status blocks, a Documentation Synchronization Contract (CLAUDE.md, ENGINEERING_GUIDELINES.md §14–§15), and `scripts/check_docs.py` enforced by a new CI `docs` job (links, anchors, status, research headers, changed-path guards). Docs and tooling only; no product change.

## Milestone 8.1 (released 2026-10-05)

Released 2026-10-05: [PR #25](https://github.com/dude297/internship-finder/pull/25) merged at the approved head `178fb47`; `main` `203a562` (post-merge CI `37386512685` green); Neon migrated `a8c3e5f7b9d1` → `b7e3d9f1a2c4`; Render `dep-db22sfvlot8c73dki4lg`; Vercel `dpl_ArUbqmusQFddZhR4GVJnUjuVrxqj`; hosted smoke 14/14. The v2 requirement scan and catalog activation are owner-gated and not yet run. Record: [deployment.md](docs/releases/2026-10-05-m8-1.md).

### Added

- Milestone 8.1: listing freshness, requirement extraction v2, and independent discovery ([ADR-015](docs/decisions/ADR-015-freshness-requirements-v2-and-independent-discovery.md)). Migration `b7e3d9f1a2c4` (CHECK only).
  - Derived listing freshness (`direct_verified`, `program_listed`, `program_recheck`, `feed_current`, `source_warning`, `manual`, `closed`) on list and detail, with per-source health on the detail page; filters **Direct ATS verified** / **Needs freshness review**; never stored, never "guaranteed open".
  - **New** badge (first found by Internship Finder < 7 days, distinct from the company's posted date), **New today / this week** filter, **Recently discovered** sort.
  - `requirements-rules` v2: enrollment/degree pursuit with application-time vs program-start timing, graduation windows, class standing, return-to-school, and a citizenship / permanent residency / U.S. person / work authorization / sponsorship split (fixes v1 labeling "citizens or permanent residents" as work authorization). 258-sentence synthetic corpus plus an adversarial suite; candidates stay pending.
  - Independent Discovery Coverage on Source Coverage (opportunities that survive without the community feed) with a direct/registry/manual/feed-only breakdown.
  - Direct Source Catalog (`backend/data/direct_source_catalog.json`, 36 officially verified boards) with **Verified Direct Sources** bulk add on the Sources page.
  - Workable and Pinpoint adapters (documented, keyless public job-board APIs).
  - An empty snapshot from a source with 10+ open postings fails instead of closing them all.
  - Research: [catalog freshness audit](docs/research/catalog-freshness-audit.md), [direct company source matrix](docs/research/direct-company-source-matrix.md), [tracker gap audit](docs/research/tracker-gap-audit.md), [extractor v2](docs/research/requirement-extractor-v2.md).

## Milestone 8 (released 2026-10-05)

Released 2026-10-05: [PR #23](https://github.com/dude297/internship-finder/pull/23) rebase-merged at the approved head `cb4f018`; `main` `9263860` (post-merge CI `37266217728` green); Neon migrated `f2a7c9d4e1b3` → `a8c3e5f7b9d1`; Render `dep-db1j19hsrm7s73bu01dg`; Vercel `dpl_CNabjmvDw2fyAus25jqVa781D1a3`; registry synced (13 programs); 6 SmartRecruiters companies activated; description coverage 22.4% → 38.7%; 18 pending suggestions, none accepted. Record: [deployment.md](docs/releases/2026-10-05-m8.md).

### Added

- Milestone 8: structured source expansion and the curated program registry ([ADR-014](docs/decisions/ADR-014-structured-source-expansion-and-program-registry.md)). Migration `a8c3e5f7b9d1` (additive; seeds the built-in registry source).
  - SmartRecruiters companies as a direct ATS source: the documented public Posting API only (`api.smartrecruiters.com`, PUBLIC postings, no key), complete paginated list walks, bounded detail requests (≤ 100 per run, reused when unchanged), detail failures make the run partial instead of erasing text or closing. Identity `smartrecruiters:<company>:<id>`; feed postings that name a SmartRecruiters posting (ID plus matching official link) are discovered, suggested, bulk-addable, and deduplicated; ATS > feed authority applies unchanged.
  - Curated program registry: a built-in, network-free source reading `backend/data/program_registry.json` (13 officially sourced programs, checked 2026-10-04). Identity `curated:<slug>:<cycle>`, idempotent re-import, removal closes, owner edits win. Verified dates fill deadline/start/end; typical windows stay text; `verify_by` drives a **Needs date verification** badge and `needs_date_verification` list filter.
  - UI: SmartRecruiters in Add Source and Source Coverage; "No confirmed deadline" vs typical-window text; an **Upcoming programs** toggle on the opportunity list.
  - Research: [provider refresh, Oracle Cloud HCM verdict, USAJOBS future card](docs/research/m8-provider-research-refresh.md) and [extractor v1 recall analysis](docs/research/requirement-extractor-recall.md) (no extractor change).

## Milestone 7.1 (released 2026-10-04)

Released 2026-10-04: [PR #19](https://github.com/dude297/internship-finder/pull/19) rebase-merged; `main` `0a636e2` (post-merge CI `37234964868` green); Neon migrated `e6d1a4b8c2f9` → `f2a7c9d4e1b3`; Render `dep-db1c2oc9v7es73eshpd0`; Vercel `dpl_AZuVPW533BkqzuzRwozvx12J5PEG`; synthetic volunteer smoke 13/13, cleaned. Record: [deployment.md](docs/releases/2026-10-04-m7-1.md).

### Added

- Milestone 7.1: volunteer opportunities. `volunteer` opportunity type (migration `f2a7c9d4e1b3`, additive, no backfill) available in manual create/edit, list, detail, eligibility, fit, and application tracking with no separate workflow; a new `opportunity_type` filter on `GET /api/opportunities` and a **Type** filter on the opportunity list. Ingestion never classifies postings as volunteer. Research only for automated volunteer sources: [docs/research/volunteer-sources-2027.md](docs/research/volunteer-sources-2027.md) (none ready).

## Milestone 7 (released 2026-10-04)

Released 2026-10-04: [PR #17](https://github.com/dude297/internship-finder/pull/17) rebase-merged at the approved head `64ce84d`; `main` `bc23629` (post-merge CI `37191644826` green); no migration; Render deploy `dep-db1bksjncjis73c2apr0`; Vercel production `dpl_Gj9D5tdBYQENGrMavySfoa3xFS57`; 20 ATS boards activated (description coverage 0.0% → 22.4%). Record: [deployment.md](docs/releases/2026-10-04-m7.md).

### Added

- Milestone 7: provider enrichment and source coverage ([ADR-013](docs/decisions/ADR-013-provider-enrichment-and-source-authority.md)). No migration.
  - Automated-source authority: direct ATS records (Greenhouse, Lever, Ashby) own canonical fields over the discovery feed; earliest record then ID within a tier; takeover by a later board, fallback to the feed from its stored payload when the board closes, and takeover again on return. Curated opportunities are never rewritten.
  - ATS source discovery derived from stored feed records (no network calls): `GET /api/sources/discovery`, `python -m app.cli source-coverage`, and owner-only bulk add `POST /api/sources/discovery/add` (max 25, `internships_only`, never syncs).
  - Source Coverage and Suggested Sources on the Sources page.
  - Scheduled and manual syncs order direct ATS sources before the feed.
  - Ashby cross-source identifier on feed postings that name an Ashby board.
  - Tests: authority, takeover/fallback stress loops, provider-identity spoofing, discovery and bulk add (including concurrency), Vitest, a Playwright enrichment scenario, and `scripts/perf_sources.py`.


### Fixed

- Provider identity patterns no longer accept a trailing newline.
- A Greenhouse feed posting whose link is on a Greenhouse board host but has a port, credentials, or a trailing-dot hostname no longer proves a Greenhouse identity (previously it skipped the conflicting-board check).
- `USERNAME_PATTERN` is anchored with `\A…\Z` (its only caller already used `fullmatch`, so no behavior change).
- The Playwright workflow spec is repeatable on a reused database.

## Milestone 6 (released 2026-10-02)

Released 2026-10-02: [PR #13](https://github.com/dude297/internship-finder/pull/13) rebase-merged at the approved head `ff47970`; `main` `80257c5` (post-merge CI `37066645594` green); Neon migrated `c5a1e0f3d7b2` → `e6d1a4b8c2f9`; Render deploy `dep-db03iknavr4c73e10b8g`; Vercel production `dpl_8kqCpb15vP5q1rcJpsSB3Pvt6XJk`; scheduled sync configured; production requirement scan run. Record: [deployment.md](docs/releases/2026-10-02-m6.md).

### Added

- Milestone 6: requirement intelligence and automation ([ADR-012](docs/decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)).
  - Migration `e6d1a4b8c2f9`: `opportunity_requirement_candidates`, `opportunities.requirements_stale_since` and `requirement_extraction_fingerprint`, and the `ashby` source kind. Additive; no backfill.
  - Deterministic requirement extractor `requirements-rules` v1 and owner review: `/api/opportunities/{id}/requirement-review` (read, refresh, one atomic batch with at most one evaluation), a Requirement Review panel, and list filters for pending suggestions, changed postings, and assessment status. Suggestions never affect eligibility until accepted; `complete` is only ever set explicitly.
  - Source-change staleness for reviewed postings, and `python -m app.cli scan-requirements` for stored opportunities.
  - Scheduled production source sync workflow (GitHub Actions, twice daily, environment-scoped secret, schema-head check) and derived source health on the Sources page.
  - Ashby public job boards (Job Postings API; listed postings only; internships only by default).
  - Deadline discovery: `deadline_within`, `has_deadline`, `sort=deadline`, "Closing soon" and "Deadline passed" badges.
  - Tests: extractor (including adversarial phrasings), candidate lifecycle, review API, staleness, discovery filters, CLI exit codes, workflow structure, Ashby adapter, source health, Vitest for the new UI, and a Playwright requirement-review scenario.
- Milestone 5: private profile source ingestion and review ([ADR-011](docs/decisions/ADR-011-profile-source-ingestion-and-review.md)).
  - Migration `c5a1e0f3d7b2`: `profile_source_artifacts` (original upload bytes in PostgreSQL), upload metadata and a per-profile SHA-256 uniqueness constraint on `profile_sources`, and `profile_facts.review_state` (backfilled so no fit input changes).
  - Deterministic résumé parser for plain text and text-based PDF (no AI, no OCR), content-sniffed, bounded, with PDF extraction in a time- and memory-limited child process.
  - `/api/profile/sources`: upload (2 MB), list, detail, download, batch review with at most one catalog pass, re-parse, delete.
  - Fit scoring reads only accepted facts; pending and rejected imported facts never score, and imported facts never touch eligibility.
  - Frontend **Imported Profile** tab for upload and review.
  - Tests: parser unit tests with synthetic text and PDF files (including a flate bomb), API and adversarial tests, migration backfill tests, Vitest, and a Playwright upload-review-delete scenario.
- Milestone 4: Match Profile, fit scoring v1, eligibility-first ranking, and internships-only board scope ([ADR-010](docs/decisions/ADR-010-fit-scoring-v1.md), [docs/scoring.md](docs/scoring.md)).
  - Migration `b41e7c9d2f60`: `profiles` fit preferences (`interests`, `preferred_locations`, `remote_preference`, `availability_start`/`end` with an end-after-start CHECK); nullable `fit_score` (0–100), `score_breakdown`, `scoring_version`, `fit_input_fingerprint` on `opportunity_evaluations` (all set or all NULL); `ingestion_sources.scope` (`all` / `internships_only`; existing sources backfilled `all`; the built-in feed must be `all`); `ingestion_runs.filtered_count`.
  - Match Profile API (`GET`/`PUT /api/profile/match`): skills, courses, projects, research, activities, experience (manual, user-verified `profile_facts`), interests, preferred locations, remote preference, availability. One atomic save replaces only the facts it owns and runs one catalog pass. Input limits on counts and lengths.
  - Deterministic fit scoring v1 (`app/opportunities/scoring/`): technical 35, academic 20, projects/research 15, interests 10, location/schedule 10, opportunity quality 10; integer half-up rounding; missing evidence scores 0 and is reported with `coverage`; lexical matching with a small alias table and punctuation-aware tokens (`c++`, `c#`, `.net`); explainable breakdown stored per evaluation.
  - Every new evaluation carries eligibility and fit. Automatic evaluation appends a row only when the eligibility or fit fingerprint changed; profile and Match Profile saves run one batched catalog pass that skips unchanged opportunities (~2 s for 1,100 synthetic opportunities locally, 0.3 s when nothing changed).
  - `GET /api/opportunities?sort=recommended`: eligible, needs verification, ineligible, not evaluated; fit inside each bucket; then posted date, first seen, ID. List items include the current fit score, coverage, and component summary; detail includes the full breakdown.
  - Greenhouse/Lever boards default to **Internships only** (whole-word title filter: intern, internship, co-op, apprentice…); **All postings** keeps everything. Filtered items are counted, never processed. Changing scope clears the HTTP validators so the next sync applies it (closing or reopening postings).
  - Frontend: Eligibility Profile / Match Profile tabs, Match Profile editor (chips and item lists, one save with a rescoring state and a waking-server message), fit badges with coverage next to eligibility, Recommended/Newest sort (recommended by default), "Why this match?" on the detail page, board scope controls and a Filtered count on the Sources page.
  - `backend/scripts/perf_smoke.py`: manual performance smoke on a disposable database.
  - Tests: scoring unit tests (components, boundaries, rounding, aliases, fingerprints), Match Profile and ranking API tests, scope ingestion/API tests, migration and constraint tests, Vitest for the new UI, and Playwright fit-ranking and board-scope scenarios.

### Changed

- Milestone 6: every adapter types an opportunity with one shared rule (structured intern field, else the internship title matcher); Greenhouse postings can now be `internship`. Only the earliest active source record rewrites a deduplicated opportunity's canonical fields. `sync-sources` prints elapsed time and an aggregate line and exits `2` for database errors.
- An eligibility-relevant profile save no longer appends an evaluation for every opportunity; only opportunities whose inputs changed get one.
- Editing an opportunity's title, organization, description, location, work mode, dates, or application URL now appends an evaluation (they are fit inputs).

- Milestone 3.5: hosted deployment foundation ([ADR-009](docs/decisions/ADR-009-hosted-deployment-architecture.md), runbook in [docs/deployment.md](docs/deployment.md)).
  - Migration `92a17353e5a8`: creates `uq_ingestion_runs_one_running_per_source` on databases migrated with the pre-merge `726372d627b8`; no-op on fresh databases; refuses (with a clear error) if duplicate `running` rows exist; the downgrade keeps the index.
  - Topology: Vercel Hobby (static build, same-origin `/api` rewrite) → Render Free (FastAPI, one instance, one worker) → Neon Free (PostgreSQL 18, direct endpoint). Manual migrations and deploys; no scheduler or keep-alive.
  - Login throttling: 10 failures per bucket and 50 in total per sliding 15 minutes, checked before password work. Requests carrying the Vercel proxy secret (`X-IF-Proxy-Secret`, from `PROXY_SHARED_SECRET`) share the `proxy` bucket, direct callers share `direct`; forwarding headers are never read (Vercel sometimes passes forged ones through).
  - Argon2 hash/verify limited to 2 concurrent operations (parameters and dummy verification unchanged).
  - `HOSTED=true`: no `/docs`, `/redoc`, `/openapi.json`; requires `SESSION_COOKIE_SECURE=true`.
  - `Cache-Control: no-store` on `/api`; `redirect_slashes=False`.
  - `DATABASE_URL` accepts Neon's `postgresql://` URL (driver scheme switched, rest untouched) for runtime, CLI, and Alembic.
  - Frontend: an unreachable backend (network error, 5xx, non-JSON wake-up page) shows "server waking up" with bounded retries and a Retry button instead of logging out.
  - `frontend/vercel.json`; Python 3.12 and Node 24.x pinned for hosting and CI.

### Fixed

- Milestone 6 final review: rejecting or editing an accepted requirement suggestion no longer deletes or rewrites a manually entered requirement, or one still shared by another accepted suggestion; `complete` is downgraded only when a reject actually removes a requirement. Ashby postings with a missing or non-boolean `isListed` are invalid items (partial run, nothing closes) instead of being imported as listed.
- Milestone 5.1: a reparse could re-propose an imported fact the owner had accepted with an edited name (facts are now keyed by the original parsed candidate). The manual-opportunity frontend test no longer races navigation.
- Greenhouse and Lever board links with credentials (`user:pw@`) or an explicit port are rejected with `422` instead of being reduced to the board name.

- Milestone 3: automated opportunity discovery and ingestion ([ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md)).
  - Migration `726372d627b8`: `ingestion_sources` (with the built-in "Tech Internship Discovery Feed"), `ingestion_runs`, `ingestion_run_errors`, `opportunity_identifiers`; `opportunities.posted_at` and `manually_curated_at`; source-record lifecycle (`ingestion_source_id`, `is_active`, `closed_at`, source dates, `content_hash`); `opportunity_evaluations.input_fingerprint`.
  - Automatic repair of development databases migrated with the pre-merge `7d7f4f8b9a3c` (restores `ck_profiles_graduation_after_status_as_of`; no manual SQL).
  - Shared ingestion pipeline: typed normalized adapter output, per-item savepoints, run history with counts and bounded safe errors, partial-success semantics, closure only after complete successful snapshots, reactivation, and conditional requests (ETag / Last-Modified → `no_change`).
  - Adapters: zshah101 discovery feed (public JSON API), Greenhouse Job Board API, Lever Postings API (global and EU). Source HTML is converted to plain text.
  - Safe HTTP client (`httpx2`, now a runtime dependency): allowlisted HTTPS hosts, public-address check, timeouts, bounded redirects/retries/size, `Retry-After`.
  - Conservative deduplication through deterministic identifiers (feed ID, Greenhouse/Lever provider IDs, exact canonical URL); identity conflicts are recorded, never merged.
  - Manual-curation protection: owner edits survive later syncs.
  - Sources API (`/api/sources`: list, add from board links, rename/enable, sync one, sync all, run history) and CLI (`sync-sources`, `sync-source`).
  - Paginated opportunity list (`limit` ≤ 100) with search and availability/source/eligibility/application/work-mode filters, freshest first.
  - Frontend: Sources page, filters and pagination, imported/manual/closed labels, Source provenance and a Review requirements action on the detail page.
  - Tests: ingestion unit and PostgreSQL tests with synthetic provider fixtures, Sources API and CLI tests, migration reconciliation tests, Vitest for the new pages, and a network-free Playwright ingestion workflow.

- Milestone 2: private single-user workflow MVP ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md)).
  - Owner authentication: Argon2id (`pwdlib[argon2]`), CLI-only account creation and password rotation (`python -m app.cli create-owner` / `set-password`), opaque server-side sessions (SHA-256 stored), HttpOnly `SameSite=Lax` cookie (`Secure` by default), HMAC-derived CSRF token on every unsafe private request, one `require_owner` boundary, generic login failures, and an in-memory failed-login throttle.
  - Migration `7d7f4f8b9a3c`: `auth_users`, `auth_sessions`, `applications`, and the `profiles` CHECK `ck_profiles_graduation_after_status_as_of`.
  - Education timeline invariant: `expected_graduation_date` must be after `education_status_as_of` when both are set (`422` from the API, CHECK constraint in PostgreSQL). Eligibility rules stay `v1`.
  - Auth reliability: a stale initial session check can't overwrite a newer login (auth generation guard), and logout keeps the user signed in with a visible error unless the server confirms it (`204`/`401`).
  - Private API: `/api/auth/*`, `GET/PUT /api/profile`, opportunity CRUD with a complete-set requirements array, `POST /api/opportunities/{id}/evaluate`, and `PUT/DELETE /api/opportunities/{id}/application`. Consistent error model (no SQL, stack traces, or echoed passwords).
  - Automatic eligibility evaluation on opportunity changes, and re-evaluation of all opportunities when an eligibility-relevant profile field changes (same transaction, history appended).
  - Manual opportunities keep provenance (`manual` source record, no fabricated external ID).
  - Application tracking (saved → withdrawn, submitted date, private notes).
  - Frontend: react-router app shell, login, profile editor, opportunity list/detail/form, structured requirement editor, plain-language eligibility explanations, projected-status notice, application tracker.
  - Playwright end-to-end workflow (Chromium) and a CI `e2e` job.
  - `compose.yaml` for a local-only PostgreSQL 18.

- Milestone 1: core domain, persistence, and eligibility v1 ([ADR-006](docs/decisions/ADR-006-core-domain-persistence-model.md)).
  - Initial Alembic migration `3b9c6b57bb60` with `profiles`, `profile_sources`, `profile_facts`, `opportunities`, `opportunity_source_records`, `opportunity_requirements`, `opportunity_evaluations`, and `eligibility_rule_results`.
  - Temporal education resolver (`app/profile/education.py`).
  - Eligibility rules v1 (ELIG-REQ-000, ELIG-AGE-001, ELIG-EDU-001, ELIG-CIT-001, ELIG-REQ-001) with the composite `evaluate_eligibility` and persistent evaluation history.
  - `opportunities.requirements_assessment_status` (`unassessed` default / `partial` / `complete`). Unassessed or partial requirement sets are at least `needs_verification` (ELIG-REQ-000), so an empty requirement list means `eligible` only when the assessment is complete.
  - CI runs migrations (upgrade, drift check, downgrade, upgrade) and integration tests against an ephemeral PostgreSQL 18 container.
- Added public-repository privacy and secret-handling safeguards.
- Milestone 0 development foundation: a React/TypeScript/Vite/Tailwind frontend (`frontend/`) that shows backend health, validated with Zod, and a FastAPI backend (`backend/`) with `GET /api/health`, a SQLAlchemy base, and an empty Alembic environment. Includes ESLint/Prettier/Vitest and Ruff/Pyright/Pytest tooling, plus a GitHub Actions CI workflow.
- Initial engineering documentation framework.
- Repository operating rules (`CLAUDE.md`, `ENGINEERING_GUIDELINES.md`).
- Project-state handoff document (`PROJECT_STATE.md`).
- Architecture decision records (ADR-001, ADR-002, ADR-003).
- ADR-004: technology stack (React/Vite/Tailwind frontend on Vercel Hobby, Python/FastAPI backend on Render Free, Neon PostgreSQL, GitHub Actions) under a $0/month, no-payment-method constraint.
- ADR-005: layered opportunity sources, time-aware eligibility, provenance-aware profile ingestion, and open-source reuse policy.

### Changed

- `GET /api/opportunities` returns a page (`{items, total, limit, offset}`) instead of an array, and each summary includes origin, availability, source names, and posted/first-seen dates.
- Automatic evaluation (opportunity create/update, sync) appends a new evaluation only when the eligibility inputs changed. `POST /api/opportunities/{id}/evaluate` still always appends. This resolves the Milestone 2 debt "updates always append an evaluation, even when only the title changed".
- The frontend calls relative `/api` URLs through a Vite proxy (same-origin). `VITE_API_BASE_URL`, the backend's `FRONTEND_ORIGIN`, and the CORS middleware were removed.
- The health-only home page was replaced by the authenticated app.

- Topic docs, `ENGINEERING_GUIDELINES.md`, `README.md`, and `PROJECT_STATE.md` updated for ADR-004/ADR-005. The planned eligibility rule ELIG-EDU-001 is now time-aware.
