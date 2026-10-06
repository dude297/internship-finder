# Project State

> The current project and production truth, for handing work to the next agent or person. Current state only: history lives in [CHANGELOG.md](CHANGELOG.md), [release records](docs/releases/), and [ADRs](docs/decisions/) ([document authority](docs/README.md)). Update it in every milestone PR and every release closeout.

<!-- BEGIN GENERATED STATUS (scripts/check_docs.py --write-status) -->
| | |
|---|---|
| **Current Production** | Milestone 11, released 2026-10-06 ([release record](docs/releases/2026-10-06-m9-m11.md)) |
| Production `main` | `cf1ad43` |
| Production schema | `a3c7e9b1d5f2` |
| **Current Development** | Milestone 15 on `feature/m15-work-authorization` |
<!-- END GENERATED STATUS -->

Last Updated: 2026-10-06

Production: https://internship-finder-pi.vercel.app (Vercel → Render → Neon). Deploy IDs, smoke results, and counts for the running release: its [release record](docs/releases/2026-10-06-m9-m11.md). Remote: https://github.com/dude297/internship-finder.

## Repository Visibility

| | |
|---|---|
| Repository visibility | **Public** (set on GitHub 2026-09-25) |
| Public repository safety | **Active** ([CLAUDE.md](CLAUDE.md#public-repository-safety), [ENGINEERING_GUIDELINES.md §16](ENGINEERING_GUIDELINES.md#16-public-repository-security-and-privacy)) |
| Private user data in Git | **Prohibited** |

Real résumé, transcript, profile, and application documents stay outside the repository, in the database or gitignored local storage. The owner's real profile is entered only through the running app. Downloaded source payloads are never committed; tests use fabricated provider fixtures.

## Current Objective

Milestones 8.2, 9, 10, 10.1, and 11 are released (2026-10-06, five deploys, [release record](docs/releases/2026-10-06-m9-m11.md)). Production runs fit scoring v2, Hide/Revert, the Action Inbox, and stale-sync/Posted-within visibility; 45 direct sources are enabled (cap 50) with 2,335 open opportunities, 56.5% independently discovered. The next steps are owner actions: review the 558 pending requirement suggestions (all v3 after the follow-up rescan; none accepted) and activate the encrypted backup.

## Status Summary

Terms: **Selected** = decided in an ADR. **Scaffolded/Implemented** = code exists in the repository and is tested. **Provisioned** = account/project/resource actually created. **Deployed** = running in a hosted environment.

| Area | Status |
|---|---|
| Technology stack | **Selected** ([ADR-004](docs/decisions/ADR-004-technology-stack.md)); hosting per [ADR-009](docs/decisions/ADR-009-hosted-deployment-architecture.md). **Provisioned and deployed** (Vercel Hobby → Render Free → Neon Free) from `main`. |
| Source/profile strategy | **Selected** ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)). Opportunity ingestion implemented (ADR-008). Résumé parser `resume-sections` v1 (ADR-011). |
| Core domain persistence | **Implemented** ([ADR-006](docs/decisions/ADR-006-core-domain-persistence-model.md), migration `3b9c6b57bb60`, immutable) |
| Authentication / private API | **Implemented and hosted** ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md), migration `7d7f4f8b9a3c`, immutable; hardened by [ADR-009](docs/decisions/ADR-009-hosted-deployment-architecture.md) §6–§7) |
| Opportunity ingestion | **Implemented and deployed** ([ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md), migration `726372d627b8`). Since Milestone 6: Ashby boards (no production Ashby source), a scheduled GitHub Actions sync (active since 2026-10-02), derived source health ([ADR-012](docs/decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)) |
| Requirement suggestions and review | **Implemented and deployed; v3 scanned** (`requirements-rules` v2 deployed 2026-10-05, v3 2026-10-06 [PR #45](https://github.com/dude297/internship-finder/pull/45); catalog scans run 2026-10-06: all stored suggestions are v3, 558 pending, 0 accepted, 0 rejected, 0 canonical; [ADR-012](docs/decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)). About 90% precision in the audit; two false-positive families await extractor v3 ([PR #45](https://github.com/dude297/internship-finder/pull/45), not merged). Suggestions never affect eligibility until accepted |
| Eligibility | **Implemented** v1 in production (rules version `v1`, unchanged by the 2026-10-06 release train); v2 (work-authorization rules ELIG-WA-001 to 005, [ADR-026](docs/decisions/ADR-026-work-authorization-eligibility.md)) is in development, unreleased, evaluated automatically (only when inputs change). Every latest evaluation is `needs_verification` until requirements are accepted |
| Fit scoring and ranking | **Implemented and deployed: scoring v2** (Milestone 11, [ADR-019](docs/decisions/ADR-019-fit-scoring-v2.md), no migration; `reevaluate` applied 2026-10-06, 2,451 evaluations, 10 scores changed all upward). v1 history rows kept ([ADR-010](docs/decisions/ADR-010-fit-scoring-v1.md), migration `b41e7c9d2f60`) |
| Owner decisions: hide and revert | **Implemented and deployed** (Milestone 9, [ADR-017](docs/decisions/ADR-017-owner-opportunity-decisions.md), migration `d4f8a1c6e2b9`): Hide/Unhide durable across syncs, Hidden filter, Revert to source (irreversible; confirmation in the UI) |
| Action Inbox and follow-ups | **Implemented and deployed** (Milestone 10, [ADR-020](docs/decisions/ADR-020-action-inbox.md), migration `a3c7e9b1d5f2`): `GET /api/inbox`, Inbox page, Next action / due / Interview at on applications |
| Data-age visibility | **Implemented and deployed** (Milestone 10.1, no migration): stale-sync banner (`/api/status/freshness`, 36 h) and the Posted-within filter |
| Direct Source Catalog activation | **Activated 2026-10-06**: 19 catalog boards added, 26 → 45 enabled direct sources plus the feed and registry (cap 50); open 1,866 → 2,335, description coverage 45.1% → 56.7%, independent discovery 44.9% → 56.5%, feed-only 1,028 → 1,016. Anduril and SpaceX fail "response too large" (20 MiB cap); Anduril is disabled ([operations.md](docs/operations.md#milestone-9-11-release-train-measurements-2026-10-06)) |
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
- Milestone 8.2 feed independence and security hardening ([PR #30](https://github.com/dude297/internship-finder/pull/30), [PR #35](https://github.com/dude297/internship-finder/pull/35), [PR #36](https://github.com/dude297/internship-finder/pull/36)); Milestone 9 owner decisions ([PR #33](https://github.com/dude297/internship-finder/pull/33)); Milestone 10 Action Inbox ([PR #38](https://github.com/dude297/internship-finder/pull/38)); Milestone 10.1 freshness visibility ([PR #42](https://github.com/dude297/internship-finder/pull/42)); Milestone 11 fit scoring v2 ([PR #37](https://github.com/dude297/internship-finder/pull/37)). All released 2026-10-06.

Per-milestone implementation and release detail: [docs/releases/](docs/releases/).

## Current Development

Milestone 15, work-authorization eligibility, on branch `feature/m15-work-authorization` (unreleased; [ADR-026](docs/decisions/ADR-026-work-authorization-eligibility.md), migration `c8d2f4a6b0e3`, eligibility rules `v2`). Release step after deploy: `reevaluate`.

None otherwise on `main`. Merged and live in production: everything through Milestone 11 plus extractor v3 and the registry re-verification (`main` `cf1ad43`). Merged but **not activated**: the encrypted weekly backup ([PR #39](https://github.com/dude297/internship-finder/pull/39), [PR #40](https://github.com/dude297/internship-finder/pull/40), [ADR-021](docs/decisions/ADR-021-encrypted-backups.md)), inert until the owner sets `BACKUP_AGE_RECIPIENT`.

Open pull requests: none.

## Known Operational Issues

- Direct sources: 45 enabled (cap 50). `greenhouse:andurilindustries` fails ("The source response is too large": 2,457 jobs exceed the 20 MiB `MAX_BYTES` cap) and is disabled; SpaceX fails the same way in a disposable-database test. Both stay in the catalog as failing entries until a size-tolerant adapter exists.
- 558 requirement suggestions are pending (all `requirements-rules` v3 after the 2026-10-06 rescan), none accepted. The deemed-export false positives (21) are gone; review the rest one by one.
- Backup is not active: no backup beyond Neon Free's short restore window until the owner installs `age`, generates a key pair into private storage, sets `BACKUP_AGE_RECIPIENT`, dispatches once, and runs a restore drill.
- Render still builds with `pip install .`; switch the build command to `pip install -r requirements.lock && pip install --no-deps .` (owner action).
- Production feed not retired. Feed-free readiness passed on disposable databases (technically GO), conditional on losing about 1,016 feed-only postings (about 800 on Workday/Oracle, which have no adapter).
- GitHub Actions: dispatch [37443083684](https://github.com/dude297/internship-finder/actions/runs/37443083684) sat "waiting" 30+ minutes with no job and was cancelled; run 37387224375 still shows queued and cannot be cancelled. Re-dispatching works (latest sync, 97.5 s ingestion for 47 sources).
- Fit v2 known gaps: multi-city locations and "United States of America" miss the Bay Area region; Foster City, San Carlos and Livermore are not in the region table; no RTL/FPGA/VLSI/PyTorch aliases; empty availability dates mean the schedule never contributes.
- Security review (2026-10-06): no BLOCKER or HIGH. MEDIUM: the login throttle shares the proxy bucket (an attacker can lock the owner out for 15 minutes; availability only). MEDIUM: Revert to source is irreversible (UI confirmation exists). LOW: the PDF child inherits the environment (deferred: see CHANGELOG Unreleased). Fixed in development: backup password via `PGPASSWORD`, CI checkout `persist-credentials: false`.

## Known Bugs

None open. Fixed during hosted validation (2026-09-29):

- **Per-client login-throttle key was forgeable through Vercel** (fixed in `36b9896`, deployed and verified). Vercel doesn't consistently overwrite a client-supplied `X-Forwarded-For` on the external rewrite, so the leftmost entry is sometimes attacker-controlled. Proxied logins now share one bucket ([ADR-009 §6 amendment](docs/decisions/ADR-009-hosted-deployment-architecture.md#6-login-rate-limiting-behind-the-proxy), [deployment.md](docs/deployment.md#production-verification)).
- Board links with credentials or a port were accepted (reduced to the board name, never fetched). Fixed in `65964c6`, deployed.

## Known Technical Debt

- The login throttle is in memory in one process ([ADR-009 §6](docs/decisions/ADR-009-hosted-deployment-architecture.md#6-login-rate-limiting-behind-the-proxy)): a deploy or restart resets it, and it needs shared state if the backend ever runs more than one worker or instance. All logins through the site share one bucket, so anyone's 10 failed attempts block new logins for up to 15 minutes (accepted; no trustworthy per-browser address exists behind Vercel's rewrite).
- Catalog re-evaluation (profile or Match Profile save) is synchronous in the request. Milestone 4 batches it and skips unchanged pairs (~2 s for 1,100 opportunities locally when everything changes; hosted, measured 2026-09-29 against 1,055 real opportunities: 6.36 s scoring everything, 2.0 s when nothing changed — see [operations.md](docs/operations.md#evaluation-history-and-re-evaluation-implemented-not-scheduled)). A much larger catalog would need background re-evaluation: the 2026-10-06 scale audit measured 42 s locally for a whole-catalog change at 10,000 opportunities, so the hosted proxy limit is reached around 3,000–5,000 ([scale audit](docs/operations.md#scale-audit-2026-10-06)).
- Fit is lexical: synonyms outside the alias and related tables don't match. Scoring v2 ([ADR-019](docs/decisions/ADR-019-fit-scoring-v2.md), in production since 2026-10-06) rejects ordinary-word uses of `Go`/`C`/`R`/`Rust` at some recall cost (no such false positives in production samples). Location matching is plain text plus a Bay Area region table (v2). Activities and experience don't score ([scoring.md](docs/scoring.md#known-limitations)).
- Every current evaluation is `needs_verification`: no imported requirement has been accepted yet, so eligibility can't be decided. Cross-bucket dominance is covered by deterministic tests, not production data.
- Source sync runs inside the HTTP request (the first discovery-feed sync takes ~20 s locally) behind Vercel's external-rewrite timeout. A timed-out proxy request may still have committed; refresh before retrying.
- Render Free cold starts take about 1–3 minutes (measured 73 s and ~3 min); Vercel either holds the request or returns `502`, which the UI shows as the waking state. Sessions survive the restart.
- Database backups: an encrypted weekly backup workflow and a restore script are implemented ([ADR-021](docs/decisions/ADR-021-encrypted-backups.md), Proposed; merged to `main` and inert) but **not activated**: until the owner sets `BACKUP_AGE_RECIPIENT`, there is no backup beyond Neon Free's short restore window. The private key is the owner's alone; losing it loses every backup.
- Board scope is title-based: internships titled without intern/co-op/apprentice words are filtered, and titles such as "Internship Program Manager" are kept. Greenhouse postings are typed by title from Milestone 6 (still `other` in production until released). Boards added before Milestone 4 were migrated to **All postings**.
- A recurring `partial` run (for example, a persistent identity conflict) blocks closure for that source until resolved.
- Title/organization search uses `ILIKE '%term%'` without a trigram index; measured < 0.5 s at 10,000 opportunities, trigram not worth it below ~50,000 ([scale audit](docs/operations.md#scale-audit-2026-10-06)).
- Every opportunity update replaces every requirement row (new IDs; old rule results keep their text with `requirement_id` NULL).
- The scheduled sync's `PRODUCTION_DATABASE_URL` uses the same Neon role as the app (full read/write, including auth and profile tables). Mitigated by the `main`-only `production` environment, SHA-pinned actions, and hash-locked dependencies; a least-privilege ingestion role and required reviewers on the environment are owner actions (security review 2026-10-06).
- Expired sessions are deleted only when that user logs in again; there's no periodic cleanup.
- `profiles` is logically a singleton, but only the service enforces that.
- Backend dependencies are hash-locked (`backend/requirements.lock`, `requirements-dev.lock`) for CI and the scheduled sync, but Render still builds with `pip install .` (range-resolved) until its build command is switched to the lock (owner action, [deployment.md](docs/deployment.md#render-internship-finder-api)).
- Nothing runs the catalog pass automatically after a rules/scoring version bump: run `python -m app.cli reevaluate` as a release step ([ADR-018](docs/decisions/ADR-018-evaluation-staleness.md); used for the Milestone 11 release on 2026-10-06). The earlier "time passes a graduation/enrollment date" debt is resolved by analysis: rules resolve status at each requirement's reference date and never read today, so time cannot make an evaluation stale.
- `work_authorization` requirements are stored but not evaluated (always `needs_verification`, ELIG-REQ-001). A design for a safe profile representation and rules exists ([research note](docs/research/work-authorization-eligibility-design.md)); nothing is implemented.
- Milestone 8: a large SmartRecruiters internship board (> 100 postings needing detail) takes several partial runs to fill, during which Source Health shows a warning and nothing closes; a SmartRecruiters company that renames its identifier closes its postings (the API answers 200 with zero postings for an unknown company); registry dates are only as current as the file (`verify_by` surfaces staleness); extractor v1 proposes a work-authorization suggestion for "citizens or permanent residents" wording (pending only; see the recall analysis); a SmartRecruiters posting whose detail fails on every run keeps its source partial, so removed postings stay open until it resolves; the list's "Needs date verification" uses the client's date and the detail page the server's UTC date (can differ near midnight); an owner edit of a registry opportunity can't clear `verify_by`/typical windows, so the badge can persist after the owner enters a confirmed deadline; `collect` sources load the source's stored raw payloads per run (bounded by the 5,000-posting cap).
- Milestone 7: a database error while applying an ADR-013 §5 fallback fails that source's whole run (the stored item already normalized once, so unlikely); the abandoned-run threshold (15 min) is shorter than the scheduled workflow timeout (20 min), so keep enabled ATS sources at or under the measured cap of 50.
- Milestone 6: the requirement extractor favors precision and misses requirements phrased unusually; a deduplicated opportunity whose earliest source has no description (the discovery feed) gets no description and therefore no suggestions from a later board record (resolved by Milestone 7's ATS authority, once released); nothing alerts when the schedule is auto-disabled after 60 days of repository inactivity (Source Health turns `stale`).

## Architecture Constraints

- Eligibility and fit are separate ([ADR-001](docs/decisions/ADR-001-separate-eligibility-and-fit.md)).
- All sources flow through a shared ingestion pipeline ([ADR-002](docs/decisions/ADR-002-shared-ingestion-pipeline.md), implemented by [ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md)).
- AI is enrichment only, not source of truth, and optional ([ADR-003](docs/decisions/ADR-003-ai-as-enrichment.md)).
- React/Vite static frontend + Python/FastAPI backend + PostgreSQL. $0/month, no payment method. Any required paid dependency needs a new ADR ([ADR-004](docs/decisions/ADR-004-technology-stack.md)).
- Time-aware eligibility, provenance-aware profile facts, layered sources, and external repos as references only ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)).
- Single-user, self-contained authentication; same-origin API; one server-side authorization boundary ([ADR-007](docs/decisions/ADR-007-single-user-auth-and-private-api.md)).
- Ingestion: adapters never touch the database; exact-identity dedup only; failed/partial runs never close postings; owner-curated content is never overwritten; outbound HTTP only to allowlisted provider hosts ([ADR-008](docs/decisions/ADR-008-opportunity-ingestion-and-deduplication.md)).

## Database State

Current (2026-10-06, after the Milestone 11 release; aggregates from the release record): migration `a3c7e9b1d5f2`; 2,451 opportunities evaluated (2,335 open at the final catalog count); 47 sources run per sync (45 enabled direct sources plus the feed and the registry); every latest evaluation is scoring v2 and `needs_verification`, with 5,771 v1 history rows kept; 0 canonical requirements; 558 pending candidates (all v3), 0 accepted, 0 rejected. Size and application counts were not re-measured. At the Milestone 8.1 release (2026-10-05): 1,847 opportunities, 28 sources, 19 pending candidates, 0 applications, 34 MB. Earlier snapshots: [archive](docs/releases/archive-project-state-2026-10-05.md).

## Current Scoring Version

`v2`, in production since 2026-10-06 (Milestone 11, [ADR-019](docs/decisions/ADR-019-fit-scoring-v2.md), same weights as v1): [docs/scoring.md](docs/scoring.md). `reevaluate` ran the same day (2,451 evaluated, 10 scores changed, all +5 to +8). v1 ([ADR-010](docs/decisions/ADR-010-fit-scoring-v1.md)) ran from the Milestone 4 release (2026-09-29); its history rows are kept. A future version bump needs `python -m app.cli reevaluate --dry-run`, then `reevaluate` ([deployment.md](docs/deployment.md#release-procedure)).

## Current Eligibility Rules Version

`v1`, implemented 2026-09-25 ([docs/eligibility.md](docs/eligibility.md)). Unchanged by the 2026-10-06 release train: eligibility digests were identical before and after the requirement scan and the scoring v2 `reevaluate`.

## Active Opportunity Sources

- Tech Internship Discovery Feed (zshah101 public JSON API) — built in, optional and supplemental; synced with the others.
- SmartRecruiters companies — 6 in production since 2026-10-05 (Internships only), and the built-in Curated Program Registry (24 programs in production since the 2026-10-06 registry sync; [research](docs/research/curated-program-expansion-2027.md)) ([docs/sources.md](docs/releases/2026-10-05-m8.md)).
- Greenhouse boards, Lever sites, and Ashby boards — 20 in production since 2026-10-04 (suggested from the feed, Internships only; [docs/sources.md](docs/releases/2026-10-04-m7.md)). Synced twice daily with the feed.
- Workable and Pinpoint: adapters since Milestone 8.1 (Pinpoint: `impulsespace`, activated 2026-10-06). 45 direct sources enabled in total (cap 50): 19 catalog boards activated 2026-10-06 (batches in the [release record](docs/releases/2026-10-06-m9-m11.md)), `andurilindustries` disabled (response over the 20 MiB cap). The Direct Source Catalog lists 64 verified boards in production (90 on this branch; the 26 new ones are not enabled, [feed-dependence-pareto-2026-10-06.md](docs/research/feed-dependence-pareto-2026-10-06.md)) (SpaceX also fails with "response too large"; [operations.md](docs/operations.md#milestone-9-11-release-train-measurements-2026-10-06)); the Curated Program Registry holds 24 programs ([docs/sources.md](docs/sources.md#direct-source-catalog-milestone-81-adr-015-6)).
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

Milestones 8.2 through 11 are released and the 2026-10-06 activation is done. Next, in order:

1. Owner: review the 558 pending requirement suggestions (v3; nothing is ever auto-accepted).
2. Owner: activate the encrypted backup (install `age`, `age-keygen` into private storage, `gh variable set BACKUP_AGE_RECIPIENT`, dispatch once, restore drill) and switch Render's build command to the lock install ([deployment.md](docs/deployment.md#render-internship-finder-api)).
3. Re-verify NIST SHIP around 2026-10-15 to 2026-10-20 (USAJOBS announcement expected).
4. Recommended next milestone: close the large-response gap (Anduril, SpaceX over the 20 MiB cap) or add Workday/Oracle coverage, which also decides whether the feed (about 1,016 feed-only postings, about 800 on Workday/Oracle) can ever be retired.

## Recent Important Decisions

- 2026-10-05: Milestone 8.1 released. PR #25 merged (merge commit) as `main` `203a562`; Neon migrated to `b7e3d9f1a2c4`; Render `dep-db22sfvlot8c73dki4lg`, Vercel `dpl_ArUbqmusQFddZhR4GVJnUjuVrxqj`; hosted smoke 14/14. v2 scan and catalog activation deferred to the owner.
- 2026-10-06: Release train: `f6210e9` (M8.2/security/CSP), M9 `4f419e5` (migration `d4f8a1c6e2b9`), M10 `1dbb86f` (migration `a3c7e9b1d5f2`), M10.1 `1d270d6`, M11 `ca8ff77`; five Render deploys, four Vercel deploys; hosted smokes all passed; v2 requirement scan and catalog activation (26 → 45 sources) run with owner authorization. [Release record](docs/releases/2026-10-06-m9-m11.md). Follow-up: extractor v3 (#45) and registry re-verification (#46) released (`cf1ad43`), rescan 563 → 558 pending (v3).
- 2026-10-06: ADR-020 accepted (Milestone 10, released): a read-only, bounded, set-based Action Inbox derived on read; three nullable follow-up columns on `applications`; fit threshold 70; hidden opportunities excluded everywhere. Migration `a3c7e9b1d5f2`.
- 2026-10-06: ADR-017 accepted (Milestone 9, released): hiding is two nullable columns that sync never touches (hidden excluded by default); Revert to source reuses the ADR-013 owner-record and fallback code and the fingerprinted evaluation. Migration `d4f8a1c6e2b9`.
- 2026-10-05: ADR-015 accepted: derived listing freshness (never stored), first-seen "New", live-link pings rejected, `requirements-rules` v2, Independent Discovery Coverage, the Direct Source Catalog, Workable and Pinpoint adapters, an empty-snapshot closure guard; no first-party company adapter yet. Migration `b7e3d9f1a2c4`.
- 2026-10-05: Milestone 8 released. PR #23 → `main` `9263860`; Neon migrated to `a8c3e5f7b9d1`; Render `dep-db1j19hsrm7s73bu01dg`, Vercel `dpl_CNabjmvDw2fyAus25jqVa781D1a3`; registry synced (13); 6 SmartRecruiters companies activated; coverage 22.4% → 38.7%. Runbook rule added: sync the feed on new code before adding sources whose feed identity that release introduces.
- 2026-10-04: ADR-014 accepted (on the Milestone 8 branch): SmartRecruiters public Posting API as an ATS source with bounded detail fetching and partial-run semantics; a multi-request `collect` adapter hook; the curated program registry as a built-in automated source (own `curated_registry` provenance, so it can update its own entries while owner edits still win); verified vs typical dates and `verify_by`. Migration `a8c3e5f7b9d1`. Oracle, Workday, USAJOBS excluded from M8.
- 2026-10-04: Milestone 7.1 released. PR #19 → `main` `0a636e2`; Neon migrated to `f2a7c9d4e1b3`; Render `dep-db1c2oc9v7es73eshpd0`, Vercel `dpl_AZuVPW533BkqzuzRwozvx12J5PEG`; synthetic volunteer smoke 13/13, cleaned.
- 2026-10-04: Milestone 7 released. PR #17 rebase-merged at approved head `64ce84d`; `main` `bc23629` (post-merge CI green). Render `dep-db1bksjncjis73c2apr0`, Vercel `dpl_Gj9D5tdBYQENGrMavySfoa3xFS57`. 20 ATS boards activated in two batches; coverage 0.0% → 22.4%.

Older decisions: the [ADRs](docs/decisions/), [CHANGELOG.md](CHANGELOG.md), and the [archive](docs/releases/archive-project-state-2026-10-05.md).
