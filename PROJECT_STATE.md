# Project State

> The current project and production truth, for handing work to the next agent or person. Current state only: history lives in [CHANGELOG.md](CHANGELOG.md), [release records](docs/releases/), and [ADRs](docs/decisions/) ([document authority](docs/README.md)). Update it in every milestone PR and every release closeout.

<!-- BEGIN GENERATED STATUS (scripts/check_docs.py --write-status) -->
| | |
|---|---|
| **Current Production** | Milestone 8.1, released 2026-10-05 ([release record](docs/releases/2026-10-05-m8-1.md)) |
| Production `main` | `203a562` |
| Production schema | `b7e3d9f1a2c4` |
| **Current Development** | none |
<!-- END GENERATED STATUS -->

Last Updated: 2026-10-05

Production: https://internship-finder-pi.vercel.app (Vercel → Render → Neon). Deploy IDs, smoke results, and counts for the running release: its [release record](docs/releases/2026-10-05-m8-1.md). Remote: https://github.com/dude297/internship-finder.

## Repository Visibility

| | |
|---|---|
| Repository visibility | **Public** (set on GitHub 2026-09-25) |
| Public repository safety | **Active** ([CLAUDE.md](CLAUDE.md#public-repository-safety), [ENGINEERING_GUIDELINES.md §16](ENGINEERING_GUIDELINES.md#16-public-repository-security-and-privacy)) |
| Private user data in Git | **Prohibited** |

Real résumé, transcript, profile, and application documents stay outside the repository, in the database or gitignored local storage. The owner's real profile is entered only through the running app. Downloaded source payloads are never committed; tests use fabricated provider fixtures.

## Current Objective

Milestone 8.1 is released (2026-10-05, [PR #25](https://github.com/dude297/internship-finder/pull/25)). Production shows derived listing freshness and Independent Discovery Coverage (732 / 1,749 open = 41.9% at release). Two owner-gated activation steps are pending: the `requirements-rules` v2 catalog scan (read-only estimate: 19 → ~244 pending suggestions) and adding Direct Source Catalog boards in batches (keep enabled direct sources ≤ 50 until re-measured).

## Status Summary

Terms: **Selected** = decided in an ADR. **Scaffolded/Implemented** = code exists in the repository and is tested. **Provisioned** = account/project/resource actually created. **Deployed** = running in a hosted environment.

| Area | Status |
|---|---|
| Technology stack | **Selected** ([ADR-004](docs/decisions/ADR-004-technology-stack.md)); hosting per [ADR-009](docs/decisions/ADR-009-hosted-deployment-architecture.md). **Provisioned and deployed** (Vercel Hobby → Render Free → Neon Free) from `main`. |
| Source/profile strategy | **Selected** ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)). Opportunity ingestion implemented (ADR-008). Résumé parser `resume-sections` v1 (ADR-011). |
| Core domain persistence | **Implemented** ([ADR-006](docs/decisions/ADR-006-core-domain-persistence-model.md), migration `3b9c6b57bb60`, immutable) |
| Authentication / private API | **Implemented and hosted** ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md), migration `7d7f4f8b9a3c`, immutable; hardened by [ADR-009](docs/decisions/ADR-009-hosted-deployment-architecture.md) §6–§7) |
| Opportunity ingestion | **Implemented and deployed** ([ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md), migration `726372d627b8`). Since Milestone 6: Ashby boards (no production Ashby source), a scheduled GitHub Actions sync (active since 2026-10-02), derived source health ([ADR-012](docs/decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)) |
| Requirement suggestions and review | **Implemented and deployed** (`requirements-rules` v2 deployed 2026-10-05; the catalog re-scan hasn't run, so stored suggestions are still v1; v1 since migration `e6d1a4b8c2f9`, applied to Neon 2026-10-02; [ADR-012](docs/decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)). Suggestions never affect eligibility until accepted |
| Eligibility | **Implemented** v1 (rules version `v1`), evaluated automatically (only when inputs change) |
| Fit scoring and ranking | **Implemented and deployed** (scoring `v1`, [ADR-010](docs/decisions/ADR-010-fit-scoring-v1.md), migration `b41e7c9d2f60`, applied to Neon 2026-09-30) |
| Application tracking | **Implemented** |
| Operating cost constraint | $0/month, no payment method required ([ADR-004](docs/decisions/ADR-004-technology-stack.md#zero-cost--no-payment-constraint)) |
| Current user education state | High-school senior (expected to become an undergraduate after graduation) |
| Product implementation | Private single-user app with automated discovery (local and hosted) |
| Profile source ingestion | **Implemented and deployed** ([ADR-011](docs/decisions/ADR-011-profile-source-ingestion-and-review.md), migration `c5a1e0f3d7b2`, applied to Neon 2026-10-01) |
| Listing freshness and independent discovery | **Implemented and deployed** (Milestone 8.1, [ADR-015](docs/decisions/ADR-015-freshness-requirements-v2-and-independent-discovery.md)): derived freshness, New/discovered filters, Independent Discovery Coverage, Direct Source Catalog (36 boards), Workable and Pinpoint adapters, empty-snapshot closure guard |
| Provider enrichment and source coverage | **Implemented, deployed, activated** (Milestone 7, released 2026-10-04, 20 production ATS boards; [ADR-013](docs/decisions/ADR-013-provider-enrichment-and-source-authority.md); no migration). ATS > feed authority with fallback, network-free ATS discovery from the feed, bulk add of suggested boards, Source Coverage on the Sources page, ATS-first sync ordering |

### Selected stack

| Layer | Selection | Implemented locally? | Provisioned? |
|---|---|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS, Zod, react-router | Yes (`frontend/`) | — |
| Frontend hosting | Vercel Hobby | — | **Yes** (project `internship-finder`, `internship-finder-pi.vercel.app`) |
| Backend | Python 3.12+, FastAPI, Pydantic, pwdlib (Argon2id), httpx2 (ingestion HTTP) | Yes (`backend/`) | — |
| Backend hosting | Render Free Web Service | — | **Yes** (`internship-finder-api`, Oregon, connected to Neon, auto-deploy off) |
| Database | Neon PostgreSQL Free (SQLAlchemy 2.x, Alembic, psycopg) | Yes (Alembic migrations; local PostgreSQL 18 via `compose.yaml`; tested on ephemeral PostgreSQL 18) | Yes (Neon Free; schema revision in the status block above) |
| CI | GitHub Actions (included free usage) | Yes (`.github/workflows/ci.yml`: frontend, backend, e2e, docs jobs on PRs and pushes to `main`; `.github/workflows/sync-production.yml`: the twice-daily production source sync) | Running on GitHub |
| End-to-end | Playwright (Chromium) | Yes (`frontend/e2e/`) | — |

## Completed Capabilities

- Engineering documentation framework and ADR-001 through ADR-005.
- Milestone 0: Development Foundation ([PR #2](https://github.com/dude297/internship-finder/pull/2)).
- Milestone 1: Core Domain, Persistence, and Eligibility v1 ([PR #4](https://github.com/dude297/internship-finder/pull/4)).
- Milestone 2: Private Single-User Workflow MVP ([PR #5](https://github.com/dude297/internship-finder/pull/5)): single-user auth, sessions, CSRF, private profile and opportunity API/UI, structured requirements, automatic eligibility evaluation, application tracking, Playwright, local PostgreSQL.
- Milestone 3: Automated Opportunity Discovery and Ingestion ([PR #6](https://github.com/dude297/internship-finder/pull/6)).
- Milestone 3.5: Hosted Deployment Foundation ([PR #7](https://github.com/dude297/internship-finder/pull/7)).
- Milestone 4: Profile Intelligence + Fit Ranking v1 ([PR #9](https://github.com/dude297/internship-finder/pull/9)).
- Milestone 5: Private Profile Source Ingestion + Review ([PR #11](https://github.com/dude297/internship-finder/pull/11)).
- Milestone 6: Requirement Intelligence and Automation ([PR #13](https://github.com/dude297/internship-finder/pull/13)).
- Milestone 7 / 7.1: Provider Enrichment and Source Authority; Volunteer Type ([PR #17](https://github.com/dude297/internship-finder/pull/17), [PR #19](https://github.com/dude297/internship-finder/pull/19)).
- Milestone 8: Structured Source Expansion + Curated Program Registry ([PR #23](https://github.com/dude297/internship-finder/pull/23)).
- Milestone 8.1: Listing Freshness, Requirement Extraction v2, Independent Discovery ([PR #25](https://github.com/dude297/internship-finder/pull/25)).

Per-milestone implementation and release detail: [docs/releases/](docs/releases/).

## Current Development

None in progress. The documentation governance change (`chore/docs-governance`) is tooling, not a milestone.

## Known Operational Issues

- SmartRecruiters `boschgroup` is still filling its detail backlog (98 postings deferred after the 2026-10-05 21:07 UTC run): runs are `partial`, Source Health shows it as failing, its ~300 postings show **Verification incomplete**, and nothing of it closes until a complete run. Expected to clear in one or two runs.
- Scheduled-sync wall time is dominated by GitHub runner queueing/setup (14 min for a 205 s sync on 2026-10-05); one post-release dispatch sat queued with no job for 36 min and was re-dispatched.
- Owner-gated, not yet run: the `requirements-rules` v2 catalog re-scan (stored suggestions are still v1) and Direct Source Catalog activation.

## Known Bugs

None open. Fixed during hosted validation (2026-09-29):

- **Per-client login-throttle key was forgeable through Vercel** (fixed in `36b9896`, deployed and verified). Vercel doesn't consistently overwrite a client-supplied `X-Forwarded-For` on the external rewrite, so the leftmost entry is sometimes attacker-controlled. Proxied logins now share one bucket ([ADR-009 §6 amendment](docs/decisions/ADR-009-hosted-deployment-architecture.md#6-login-rate-limiting-behind-the-proxy), [deployment.md](docs/deployment.md#production-verification)).
- Board links with credentials or a port were accepted (reduced to the board name, never fetched). Fixed in `65964c6`, deployed.

## Known Technical Debt

- The login throttle is in memory in one process ([ADR-009 §6](docs/decisions/ADR-009-hosted-deployment-architecture.md#6-login-rate-limiting-behind-the-proxy)): a deploy or restart resets it, and it needs shared state if the backend ever runs more than one worker or instance. All logins through the site share one bucket, so anyone's 10 failed attempts block new logins for up to 15 minutes (accepted; no trustworthy per-browser address exists behind Vercel's rewrite).
- Catalog re-evaluation (profile or Match Profile save) is synchronous in the request. Milestone 4 batches it and skips unchanged pairs (~2 s for 1,100 opportunities locally when everything changes; hosted, measured 2026-09-29 against 1,055 real opportunities: 6.36 s scoring everything, 2.0 s when nothing changed — see [operations.md](docs/operations.md#evaluation-history-and-re-evaluation-implemented-not-scheduled)). A much larger catalog would need background re-evaluation.
- Fit v1 is lexical: synonyms outside the alias table don't match, and a skill that's also a common word (e.g. `Go`) can match unrelated text. Location matching is plain text. Activities and experience don't score ([scoring.md](docs/scoring.md#known-limitations-v1)).
- Every current evaluation is `needs_verification`: no imported requirement has been accepted yet, so eligibility can't be decided. Cross-bucket dominance is covered by deterministic tests, not production data.
- Source sync runs inside the HTTP request (the first discovery-feed sync takes ~20 s locally) behind Vercel's external-rewrite timeout. A timed-out proxy request may still have committed; refresh before retrying.
- Render Free cold starts take about 1–3 minutes (measured 73 s and ~3 min); Vercel either holds the request or returns `502`, which the UI shows as the waking state. Sessions survive the restart.
- No database backups beyond Neon Free's short restore window.
- Board scope is title-based: internships titled without intern/co-op/apprentice words are filtered, and titles such as "Internship Program Manager" are kept. Greenhouse postings are typed by title from Milestone 6 (still `other` in production until released). Boards added before Milestone 4 were migrated to **All postings**.
- A recurring `partial` run (for example, a persistent identity conflict) blocks closure for that source until resolved.
- Deleting an imported opportunity deletes its source records, so the next sync re-imports it (no "hide" yet). There's no "revert to source" for curated opportunities.
- Title/organization search uses `ILIKE '%term%'` without a trigram index; fine at thousands of rows.
- Every opportunity update replaces every requirement row (new IDs; old rule results keep their text with `requirement_id` NULL).
- Expired sessions are deleted only when that user logs in again; there's no periodic cleanup.
- `profiles` is logically a singleton, but only the service enforces that.
- Backend dependencies are range-pinned in `pyproject.toml` without a lock file, so backend installs aren't fully reproducible. The frontend has `package-lock.json`.
- Nothing re-evaluates when the eligibility rules version changes or when time passes an expected graduation/enrollment date.
- `work_authorization` requirements are stored but not evaluated (always `needs_verification`, ELIG-REQ-001).
- Milestone 8: a large SmartRecruiters internship board (> 100 postings needing detail) takes several partial runs to fill, during which Source Health shows a warning and nothing closes; a SmartRecruiters company that renames its identifier closes its postings (the API answers 200 with zero postings for an unknown company); registry dates are only as current as the file (`verify_by` surfaces staleness); extractor v1 proposes a work-authorization suggestion for "citizens or permanent residents" wording (pending only; see the recall analysis); a SmartRecruiters posting whose detail fails on every run keeps its source partial, so removed postings stay open until it resolves; the list's "Needs date verification" uses the client's date and the detail page the server's UTC date (can differ near midnight); an owner edit of a registry opportunity can't clear `verify_by`/typical windows, so the badge can persist after the owner enters a confirmed deadline; `collect` sources load the source's stored raw payloads per run (bounded by the 5,000-posting cap).
- Milestone 7: a database error while applying an ADR-013 §5 fallback fails that source's whole run (the stored item already normalized once, so unlikely); the abandoned-run threshold (15 min) is shorter than the scheduled workflow timeout (20 min), so keep enabled ATS sources at or under the measured cap of 50.
- Milestone 6: the requirement extractor favors precision and misses requirements phrased unusually; a deduplicated opportunity whose earliest source has no description (the discovery feed) gets no description and therefore no suggestions from a later board record (resolved by Milestone 7's ATS authority, once released); the scheduled workflow installs range-pinned backend dependencies (no lockfile); nothing alerts when the schedule is auto-disabled after 60 days of repository inactivity (Source Health turns `stale`).

## Architecture Constraints

- Eligibility and fit are separate ([ADR-001](docs/decisions/ADR-001-separate-eligibility-and-fit.md)).
- All sources flow through a shared ingestion pipeline ([ADR-002](docs/decisions/ADR-002-shared-ingestion-pipeline.md), implemented by [ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md)).
- AI is enrichment only, not source of truth, and optional ([ADR-003](docs/decisions/ADR-003-ai-as-enrichment.md)).
- React/Vite static frontend + Python/FastAPI backend + PostgreSQL. $0/month, no payment method. Any required paid dependency needs a new ADR ([ADR-004](docs/decisions/ADR-004-technology-stack.md)).
- Time-aware eligibility, provenance-aware profile facts, layered sources, and external repos as references only ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)).
- Single-user, self-contained authentication; same-origin API; one server-side authorization boundary ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md)).
- Ingestion: adapters never touch the database; exact-identity dedup only; failed/partial runs never close postings; owner-curated content is never overwritten; outbound HTTP only to allowlisted provider hosts ([ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md)).

## Database State

Current (2026-10-05, at the Milestone 8.1 release): migration `b7e3d9f1a2c4`; 1,847 opportunities (1,749 open); 1,955 source records; 28 ingestion sources; 7,257 evaluations, every latest `needs_verification`; 0 canonical requirements; 19 pending candidates (all v1); 0 applications; 34 MB. Earlier snapshots: [archive](docs/releases/archive-project-state-2026-10-05.md).

## Current Scoring Version

`v1`, in production since the Milestone 4 release (2026-09-29): [docs/scoring.md](docs/scoring.md), [ADR-010](docs/decisions/ADR-010-fit-scoring-v1.md).

## Current Eligibility Rules Version

`v1`, implemented 2026-09-25 ([docs/eligibility.md](docs/eligibility.md)). Unchanged by Milestones 2 and 3 (only when evaluations run changed).

## Active Opportunity Sources

- Tech Internship Discovery Feed (zshah101 public JSON API) — built in, optional and supplemental; synced with the others.
- SmartRecruiters companies — 6 in production since 2026-10-05 (Internships only), and the built-in Curated Program Registry (13 programs) ([docs/sources.md](docs/releases/2026-10-05-m8.md)).
- Greenhouse boards, Lever sites, and Ashby boards — 20 in production since 2026-10-04 (suggested from the feed, Internships only; [docs/sources.md](docs/releases/2026-10-04-m7.md)). Synced twice daily with the feed.
- Workable and Pinpoint: adapters available since Milestone 8.1; none configured. The Direct Source Catalog lists 36 verified boards (3 configured: Waymo, Lyft, Coinbase) for owner-approved activation ([docs/sources.md](docs/sources.md#direct-source-catalog-milestone-81-adr-015-6)).
- Manual entry.
- Excluded: `SuryaHarikrishnan/2027-internship-tracker` listing data (licensing unclear).

Details, licensing basis, and attribution: [docs/sources.md](docs/sources.md).

## Environment / Deployment Notes

- Backend variables: `DATABASE_URL` (required except for `/api/health`), `SESSION_TTL_HOURS`, `SESSION_COOKIE_SECURE`, hosted-only `HOSTED` and `PROXY_SHARED_SECRET`, and the test-only `INGESTION_FIXTURE_FILE` (never set for real use). The frontend has no build-time variables; Vercel Production holds `PROXY_SHARED_SECRET` for the `/api` rewrite. See [docs/development.md](docs/development.md#environment-variables).
- Hosting (ADR-009): Vercel Hobby `internship-finder` → Render Free `internship-finder-api` (Oregon) → Neon Free. Deploys are manual: migrate → Render → Vercel ([docs/deployment.md](docs/deployment.md)). The owner confirmed the Vercel plan (Hobby, no payment method) on 2026-09-28.
- Each provisioning step must confirm that no payment method is required before creating the account or project.

## Deferred Work

- Deployment workflows (deploys stay manual).
- Early-college/research-program sources (layer 3). Ashby and scheduled sync are implemented in Milestone 6.

## Next Planned Task

Milestone 8.1 is released. Pending, owner-approved only:

1. Run the `requirements-rules` v2 catalog scan (`python -m app.cli scan-requirements`; read-only estimate 19 → ~244 pending suggestions, nothing auto-accepted).
2. Add Direct Source Catalog boards from **Verified Direct Sources** in batches, keeping enabled direct sources ≤ 50 until a scheduled run is re-measured.

Also watch Bosch's backlog (98 deferred at 2026-10-05 21:07 UTC) clear and its Source Health return to healthy. Recommended next milestone: a source-retirement command and a feed-free first run ([ADR-015 §11](docs/decisions/ADR-015-freshness-requirements-v2-and-independent-discovery.md)).

## Recent Important Decisions

- 2026-10-05: Milestone 8.1 released. PR #25 merged (merge commit) as `main` `203a562`; Neon migrated to `b7e3d9f1a2c4`; Render `dep-db22sfvlot8c73dki4lg`, Vercel `dpl_ArUbqmusQFddZhR4GVJnUjuVrxqj`; hosted smoke 14/14. v2 scan and catalog activation deferred to the owner.
- 2026-10-05: ADR-015 accepted: derived listing freshness (never stored), first-seen "New", live-link pings rejected, `requirements-rules` v2, Independent Discovery Coverage, the Direct Source Catalog, Workable and Pinpoint adapters, an empty-snapshot closure guard; no first-party company adapter yet. Migration `b7e3d9f1a2c4`.
- 2026-10-05: Milestone 8 released. PR #23 → `main` `9263860`; Neon migrated to `a8c3e5f7b9d1`; Render `dep-db1j19hsrm7s73bu01dg`, Vercel `dpl_CNabjmvDw2fyAus25jqVa781D1a3`; registry synced (13); 6 SmartRecruiters companies activated; coverage 22.4% → 38.7%. Runbook rule added: sync the feed on new code before adding sources whose feed identity that release introduces.
- 2026-10-04: ADR-014 accepted (on the Milestone 8 branch): SmartRecruiters public Posting API as an ATS source with bounded detail fetching and partial-run semantics; a multi-request `collect` adapter hook; the curated program registry as a built-in automated source (own `curated_registry` provenance, so it can update its own entries while owner edits still win); verified vs typical dates and `verify_by`. Migration `a8c3e5f7b9d1`. Oracle, Workday, USAJOBS excluded from M8.
- 2026-10-04: Milestone 7.1 released. PR #19 → `main` `0a636e2`; Neon migrated to `f2a7c9d4e1b3`; Render `dep-db1c2oc9v7es73eshpd0`, Vercel `dpl_AZuVPW533BkqzuzRwozvx12J5PEG`; synthetic volunteer smoke 13/13, cleaned.
- 2026-10-04: Milestone 7 released. PR #17 rebase-merged at approved head `64ce84d`; `main` `bc23629` (post-merge CI green). Render `dep-db1bksjncjis73c2apr0`, Vercel `dpl_Gj9D5tdBYQENGrMavySfoa3xFS57`. 20 ATS boards activated in two batches; coverage 0.0% → 22.4%.

Older decisions: the [ADRs](docs/decisions/), [CHANGELOG.md](CHANGELOG.md), and the [archive](docs/releases/archive-project-state-2026-10-05.md).
