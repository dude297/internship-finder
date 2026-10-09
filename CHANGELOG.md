# Changelog

All notable changes to this project are documented here.

## Unreleased

### Changed

- Operational cap on enabled direct sources raised 50 → 100 (`MAX_ENABLED_DIRECT_SOURCES`, Sources page `DIRECT_SOURCE_CAP`) from production measurements: 47 sources synced in 152.9 s; 100 project to 5–7 minutes, under the 15-minute abandoned-run threshold ([operations.md](docs/operations.md#operational-source-cap)).

## Milestones 12–19 (released 2026-10-06)

Released 2026-10-06 as one deploy of `main` `8ea9fea` (Render `dep-db2ngbrncjis73boa6qg`, Vercel `internship-finder-ncm5ju482`); Neon `a3c7e9b1d5f2` → `c9e2b7a4d1f8`; `reevaluate` for eligibility rules `v2` (2,472 evaluated). Record: [2026-10-06-m12-m19.md](docs/releases/2026-10-06-m12-m19.md).

### Added

- Milestone 18, source quality and supply intelligence (no migration; [ADR-025 amendment](docs/decisions/ADR-025-dashboard-and-application-engine-v2.md)): the dashboard's Discovery section gains a New supply block: new open opportunities today and this week (client time zone), how many of those this week were found independently of the community feed, new this week by source kind (top 5), closing-soon count, and an 8-week trend of new opportunities (inline SVG with a text equivalent; includes ones that have since closed; hidden excluded). "Descriptions gained" is not shown because no description history exists. Two extra aggregate statements.
- Milestone 16: Home Dashboard and Application Engine v2 ([ADR-025](docs/decisions/ADR-025-dashboard-and-application-engine-v2.md)). Migration `c9e2b7a4d1f8` (additive: `applications.applied_at`, `application_events`).
  - Application history: meaningful changes (created, status, next action, follow-up date, interview scheduled/updated, note added, offer received) are recorded in the same transaction; no history is invented for existing applications. `applied_at` is stamped when an application first becomes applied and can be corrected.
  - `GET /api/applications` (filters and sorts), `GET /api/applications/{id}/events`, and `GET /api/dashboard` (actions, pipeline counts, new high-fit, upcoming, discovery health, requirement suggestions, outcome funnel; rates only with at least 5 applications, medians only with at least 3 timed ones).
  - **Dashboard** (`/dashboard`, now the default page after login) and **Applications** (`/applications`: List and Pipeline views, stage selector, quick actions) pages, a History timeline and **Applied at** on the application detail, and Dashboard/Applications navigation.
- Milestone 19, Sources page clarity pass (frontend only, no API or migration change): a four-number coverage summary on top (Independent discovery %, Description coverage %, feed-only postings, enabled direct sources against the recommended cap of 50 from [operations.md](docs/operations.md#operational-source-cap), a frontend constant); the detailed tiles and provider table moved into a disclosure. Sources are grouped by health, failing first, then warning (partly succeeded or stale), healthy, and not running, each card showing the last error, the last attempt and the last success; the last error is no longer printed twice. Suggested Sources are ordered by feed-only postings (configured last) with a short explanation; Verified Direct Sources list unconfigured boards first and say how many remain. Clear empty states, monospace for board keys and identifiers, and horizontal scroll contained inside the tables so a 390px screen doesn't overflow. Add source, enable/disable, import scope, bulk add and the run summary are unchanged.
- Milestone 19, UX and accessibility final pass (frontend only, no API or migration change): the main navigation is ordered Dashboard, Inbox, Opportunities, Review, Applications, Profile, Sources and sits on its own row under the brand and Log out, so it no longer wraps awkwardly at 390px or 1024px; the Applications pipeline uses two columns at tablet and three at desktop width instead of six cramped ones; the Applications intro sentence is fixed; the Review keyboard-shortcut hints wrap instead of overflowing a 390px screen; long titles break inside narrow review cards; Profile tabs wrap. New `e2e/a11y.spec.ts` runs axe (`@axe-core/playwright`, dev dependency) on every route and asserts no horizontal overflow at five widths.
- Milestone 19, Inbox and Opportunities UX pass (frontend only, no API or migration change): the Opportunities filters keep eight everyday filters visible and put the other seven under "More filters" (open automatically when one is active, with a count), plus a Clear filters button that also empties the search box, so a 390px screen shows results after one screen instead of fifteen selects; the Fit and eligibility badges stay on one row on mobile; the empty state links to Sources. On the opportunity detail page the application tracker moved up under Eligibility and the six fit components sit in a "Score breakdown by component" disclosure (the score, coverage and scoring version stay visible). Cards use the shared 10px card radius. No function removed.
- Milestone 19, freshness wording and Inbox dates (frontend only, no API, migration, or semantics change): freshness labels are plain language ("Confirmed on company board · 3h ago", "Seen in community feed only", "Company board check pending"; same states and tooltips), the opportunity detail shows freshness once (compact header badge plus the Freshness section; per-source sync health moved onto the Source cards), Inbox items show a human date ("Tue, Mar 12 · in 2 days") and the application kind, empty Inbox sections collapse to one line, "Review requirements" and "Edit" are one link (the requirement queue has no per-opportunity filter in the UI) with Delete pushed apart, and list cards group badges into a priority row (eligibility, fit, deadline) and a muted row.

- Work-authorization eligibility ([ADR-026](docs/decisions/ADR-026-work-authorization-eligibility.md), Milestone 15; eligibility `RULES_VERSION` `v2`): the owner can record seven separate, explicit, nullable answers (authorized to work in the U.S., needs sponsorship now, may need it later, U.S. citizen, U.S. permanent resident, U.S. person for export control, active security clearance; each defaults to "Prefer not to say / not provided") in a new Work authorization section of the profile. Accepted requirements with the extractor's five fixed labels are evaluated by ELIG-WA-001 to ELIG-WA-005, only against the matching answer; nothing is derived from another answer, and a missing answer stays `needs_verification`. Migration `c8d2f4a6b0e3` (seven nullable boolean `profiles` columns, no backfill; written against head `a3c7e9b1d5f2`). Extractor unchanged. **Release step:** after deploy, `python -m app.cli reevaluate --dry-run`, then `reevaluate`.

- Large-board Greenhouse sources ([ADR-022](docs/decisions/ADR-022-large-board-greenhouse.md), Proposed; Milestone 12, no migration): a board with at most 500 stored jobs is still one conditional `?content=true` request (ETag/Last-Modified, `no_change` on 304, validators kept). A board with more stored jobs, or one whose content list is over the cap or lists more than 500 jobs, reads the ~2.5 MB content-free `/jobs` list as the complete snapshot (`meta.total` checked, duplicate ids and more than 10,000 jobs refused) plus one `/jobs/<id>` per internship-titled job (Anduril, SpaceX), with fixed bounds (100 detail attempts including failures, 1 MiB per detail, 8 MiB and a 120 s deadline of detail per run, stop after 5 failures in total) and reuse of stored text while the `updated_at` the text belongs to (`_content_updated_at`) is unchanged, so a failed or deferred refetch is retried next run. A detail that isn't fetched never closes or fails anything. The 20 MiB per-request cap is unchanged; `fetch_json` gains a tightening-only `max_bytes`, `Fetched.size`, and an optional `deadline`; a collect adapter may return a `Fetched` so the pipeline keeps validators. Tests: a compression bomb is capped on decoded bytes.

- Milestone 14, Requirement Review Workbench ([ADR-024](docs/decisions/ADR-024-requirement-review-workbench.md); no migration, no new dependency, extraction and eligibility unchanged): a **Review** page (`/requirements`, linked from the Inbox) to work the pending-suggestion backlog across opportunities. `GET /api/requirement-review/queue` (paged to at most 100, filters on category, extractor name/version, organization, source kind, opportunity, posting changed, and first-proposed date; constant statement count) returns each suggestion with its evidence sentence, opportunity and freshness, the opportunity's existing requirements, a duplicate flag, and a progress summary (pending total, category distribution, reviewed today). Accept, Edit + Accept, Reject, Skip and Previous/Next with keyboard shortcuts (`A` `E` `R` `S` `J` `K`, off while typing); accept and single reject use the existing atomic review endpoint. `POST /api/requirement-review/reject-batch` rejects 1 to 100 selected pending suggestions all-or-nothing behind a confirmation. There is no accept-all or auto-accept. "Reviewed today" is derived from `updated_at` (no review timestamp is stored), so it is approximate.
- Frontend: design tokens, public landing page at `/` for logged-out visitors, redesigned login with waking-server, rate-limit and unavailable states, `IF` mark and favicon, light AppShell nav pass. No backend or API changes.
- Direct Source Catalog: 26 more verified boards (64 to 90; Greenhouse 20, Ashby 5, Lever 1), mostly space, robotics, fusion/quantum, AI-hardware, and quant-with-hardware employers (e.g. Muon Space, K2 Space, General Matter, Graphcore, IMC, Virtu), each checked against its provider's documented API on 2026-10-06. None are enabled; enabling all would pass the 50-source cap. No migration.
- `backend/scripts/feed_pareto.py`: read-only report of how much of the public community feed is not covered by a direct source (status, provider histogram, top organizations, unconfigured supported boards). Analysis: [feed-dependence-pareto-2026-10-06.md](docs/research/feed-dependence-pareto-2026-10-06.md) (68% of the feed's listings are Workday or Oracle HCM, which the app does not support).

### Changed

- Frontend performance and test reliability (chore, no API or migration change): authenticated pages are code-split with `React.lazy` (entry chunk 485 kB / 141 kB gzip to 392 kB / 119 kB gzip; landing and login stay in the entry chunk). Vitest flakes under parallel load fixed at the root: `findBy`/`waitFor` default raised to 10 s in `tests/setup.ts`, real timers restored after each test, and the source-scope test no longer indexes `listitem` before the list is complete or reads `calls.at(-1)`. Conventions in [development.md](docs/development.md#test-boundary-unit-vs-postgresql-vs-end-to-end).

### Documentation

- Research note [m13-workday-oracle-provider-gate.md](docs/research/m13-workday-oracle-provider-gate.md): Workday (YELLOW: robots-advertised sitemap capped at 100 URLs plus JobPosting JSON-LD), Oracle Recruiting Cloud (RED), 14 ATS families (Personio and Teamtailor GREEN pending governance), and mega-cap career sites. No code or behavior change.

### Security

- Pre-release hardening (security review of `cf1ad43..main`, verdict safe to release): the scheduled sync logs which credential it uses (a notice for `SYNC_DATABASE_URL`, a warning on the full-privilege fallback); an application save locks its row before the `expected_updated_at` check; `interview_at` and `next_action_due` are bounded to 2000-2999 like `applied_at`; the backup masks the decoded database password.
- Least-privilege database role for the scheduled sync ([ADR-027](docs/decisions/ADR-027-least-privilege-sync-role.md), Proposed; **not activated**, nothing run against Neon): `scripts/sql/sync_role_grants.sql` creates `if_sync` (no password in the file; created in SQL because console/CLI-created Neon roles join `neon_superuser`) and grants it table by table only what `sync-sources --scheduled` uses, with no access to `auth_users`, `auth_sessions`, `profile_sources`, `profile_source_artifacts`, or `applications`. `backend/tests/test_sync_role.py` runs the sync as that role against PostgreSQL, proves the denials, and fails when a new table is neither granted nor excluded. `sync-production.yml` prefers a `SYNC_DATABASE_URL` environment secret and falls back to `PRODUCTION_DATABASE_URL`, so nothing changes until the owner follows the runbook in [operations.md](docs/operations.md#least-privilege-sync-role-owner-action-not-activated). `.gitignore` now allows `scripts/sql/*.sql` (all other `*.sql` stay ignored). No migration.
- CI: every `actions/checkout` now sets `persist-credentials: false` (the backend, e2e, and docs jobs kept the token in `.git/config`).
- `scripts/backup_db.sh` passes the database password to `psql`/`pg_dump` through `PGPASSWORD` instead of the URL on the command line (argv is readable by other processes); an execution test checks argv on Linux.
- Deferred: minimizing the PDF child's environment. Code execution inside the child could read `/proc/self/environ` anyway, so clearing `os.environ` adds little; a real fix means replacing the `multiprocessing` isolation with an `exec` that takes an explicit environment.

### Changed

- The application PUT's `status` is optional (omitted = unchanged) and accepts `expected_updated_at` (409 when stale); `GET /api/dashboard` and `GET /api/applications` accept `tz_offset_minutes`.
- The post-login landing page and the unknown-route fallback are `/dashboard` instead of `/opportunities`. `InboxItem` gains an optional `kind`; `ApplicationResponse` gains `id`, `opportunity_id`, `applied_at`.

## Milestones 8.2, 9, 10, 10.1, and 11 (released 2026-10-06)

Released 2026-10-06 in five deploys: `main` `f6210e9` (Milestone 8.2, security hardening, CSP, registry and catalog data; post-merge CI `37435960967`); Milestone 9 [PR #33](https://github.com/dude297/internship-finder/pull/33) `4f419e5` (Neon `b7e3d9f1a2c4` → `d4f8a1c6e2b9`); Milestone 10 [PR #38](https://github.com/dude297/internship-finder/pull/38) `1dbb86f` (→ `a3c7e9b1d5f2`); Milestone 10.1 [PR #42](https://github.com/dude297/internship-finder/pull/42) `1d270d6`; Milestone 11 fit scoring v2 [PR #37](https://github.com/dude297/internship-finder/pull/37) `ca8ff77` (post-merge CI `37450518492`), followed by `reevaluate` (2,451 evaluations). Activation: requirements v2 scan (563 pending, none accepted) and 19 catalog boards (26 → 45 direct sources). The encrypted backup code is merged but inert until the owner configures it. Record: [2026-10-06-m9-m11.md](docs/releases/2026-10-06-m9-m11.md).

### Added

- Fit scoring v2 ([ADR-019](docs/decisions/ADR-019-fit-scoring-v2.md), Milestone 11; `SCORING_VERSION` `v2`, weights unchanged, no migration, no frontend change): ambiguous-skill guard for `Go`/`C`/`R`/`Rust` (no more `go-to-market`, `C-suite`, `rust-proof` evidence), reviewed aliases (SystemVerilog, PCB/printed circuit board, python3, cpp) and one-way Machine Learning to deep learning/neural network, course subject groups, Bay Area region and remote-from-text locations, each explained in the breakdown. Synthetic benchmark (58 postings, two profiles) in the tests. Applied 2026-10-06 with `reevaluate` (2,451 evaluated; 10 scores changed, all upward).
- Encrypted database backup ([ADR-021](docs/decisions/ADR-021-encrypted-backups.md), Proposed): `.github/workflows/backup-production.yml` (weekly + dispatch, `main`/`production` only) streams `pg_dump | age` with a public recipient key (`BACKUP_AGE_RECIPIENT`, no decryption key in CI) into a 14-day artifact; `scripts/backup_db.sh`, `scripts/restore_backup.sh` (refuses a non-empty target), a workflow-invariants test, and a restore runbook in [operations.md](docs/operations.md#database-backup-implemented-not-activated-until-the-owner-configures-it). Inert until the owner configures the key. No migration.
- Direct Source Catalog: 28 verified boards (36 → 64), student-relevant aerospace, robotics, AI-hardware, semiconductor, quantum, and energy employers (e.g. Rocket Lab, Zipline, Astranis, Neuralink, Etched, Quantinuum, Shield AI, Saronic), each re-verified against its provider's documented API on 2026-10-06; 19 were activated the same day (Anduril fails "response too large", 20 MiB cap, and is disabled) ([research](docs/research/direct-source-expansion-2026-10-06.md)).
- Milestone 8.2 (true feed independence, [ADR-016](docs/decisions/ADR-016-source-retirement-and-feed-free-bootstrap.md)): `python -m app.cli retire-source SOURCE [--apply]` closes a source's records through the pipeline's normal closure and fallback path, then disables it (dry run by default, atomic, idempotent); `bootstrap-sources` sets up a new installation from the Direct Source Catalog without the community feed (cap 50, never syncs unless `--sync`). The pipeline's closure is extracted into `close_records`, unchanged. No migration.
- Milestone 10: Action Inbox and application follow-up ([ADR-020](docs/decisions/ADR-020-action-inbox.md)). Migration `a3c7e9b1d5f2` (three nullable columns).
  - `GET /api/inbox` and an **Inbox** page: new high-fit (fit >= 70, first found within 7 days), closing soon (verified deadline within 14 days), requirements pending review, source warnings, program `verify_by` due, and applications needing attention (next action due within 3 days, interview within 7 days, saved/applying untouched for 14 days). Bounded to 10 items per section, constant statement count, hidden opportunities excluded.
  - Application tracking: **Next action**, **Next action due**, **Interview at**.
- Milestone 10.1, data-age visibility (no migration): an app-wide banner when the newest successful sync of any enabled automated source is older than 36 h (`GET /api/status/freshness`, one statement), and a **Posted** filter (`posted_within=7|30|90`; opportunities with no posted date are excluded only while the filter is set).
- Milestone 9: owner decisions on opportunities ([ADR-017](docs/decisions/ADR-017-owner-opportunity-decisions.md)). Migration `d4f8a1c6e2b9` (two nullable columns).
  - **Hide / Unhide** an opportunity (`PUT`/`DELETE /api/opportunities/{id}/dismissal`): durable across syncs (source records keep updating; never re-imported as new), excluded from the default list and the recommended sort; a **Hidden** filter (`hidden=include|only`) shows them.
  - **Revert to source** (`POST /api/opportunities/{id}/revert-to-source`) for curated imported opportunities: after confirmation, discards edits and recorded requirements and restores the authoritative active source's content, then re-evaluates; refused for manual-only opportunities.
- Curated Program Registry: 11 programs for the 2027 cycle usable by a high-school senior or incoming first-year (NIH SIP, Navy SEAP, NIST SHIP, Microsoft Discovery, Jane Street WiSE, CRA-WP DREU, Google Summer of Code, NASA Space Apps, BNL User Facility Summer School, NSF REU sites directory, FIRST volunteering); verified dates only where the official page prints them, otherwise typical windows with `verify_by` ([research](docs/research/curated-program-expansion-2027.md)).
- Evaluation staleness ([ADR-018](docs/decisions/ADR-018-evaluation-staleness.md)): `python -m app.cli reevaluate [--stale-only] [--dry-run] [--batch-size N]` (a release step after a rules/scoring version bump) and tests that both version bumps re-evaluate every opportunity. Time-triggered re-evaluation is unnecessary (rules never read today). No fingerprint change, no migration. Research: [work-authorization eligibility design](docs/research/work-authorization-eligibility-design.md) (design only).

### Changed

- Curated Program Registry re-verified 2026-10-06 against the official pages: Tech Interactive holiday teen volunteers now carry verified application dates (Oct 9 to Oct 23, 2026), DOE SULI Summer 2027 now carries verified open (2026-10-14) and deadline (2027-01-06), MIT PRIMES re-checked (open, Nov 2, 2026 deadline); NASA Space Apps, Navy SEAP, and NIST SHIP unchanged. Data only; no code or migration.
- Requirement extractor `requirements-rules` 2 -> 3 (production audit of pending suggestions): "must either be a U.S. person ... or otherwise eligible for deemed export licensing" no longer proposes `U.S. person (export control)` (an either/or, not a requirement), and a clause that both states a requirement and says the employer "does not provide visa sponsorship" now proposes both (previously only the sponsorship label, because the negation guard saw "does not"). Suggestions stay pending-only. The version bump makes `scan-requirements` re-process stored opportunities (owner-run after release; reviewed decisions are untouched). No migration.
- Fit scoring v2 review fixes (same `v2`): related skill terms are looked up through any alias (`ML`/`AI` get deep-learning credit like `Machine Learning`); ambiguous-skill context words no longer include `skills`/`tools`/`analysis`/`statistics`/`language`/`stack`/`tech`, and `Series C`, `Objective-C`, `vitamin C`, `we go build` are rejected; Bay Area region accepts `SF Bay Area`, `Greater Bay Area`, and Bay Area ZIP codes (`94xxx`/`95xxx`; a ZIP elsewhere such as `Oakland 10001` does not match). README now says fit scoring v2.
- Frontend responses send a strict Content-Security-Policy and a Permissions-Policy (security review L3); verified against the production build with zero violations. Live since the 2026-10-06 Vercel deploy.
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
