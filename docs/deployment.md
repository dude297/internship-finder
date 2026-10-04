# Deployment

Hosted architecture: [ADR-009](decisions/ADR-009-hosted-deployment-architecture.md). This file is the runbook. It never contains secrets: no `DATABASE_URL`, proxy secret, password, hash, session or CSRF token.

## Status (2026-10-04)

| Part | State |
|---|---|
| Neon | **Provisioned.** Migrated to `f2a7c9d4e1b3` on 2026-10-04 (Milestone 7.1, `alembic check` clean). Owner created (CLI, `getpass`). 1,193 opportunities (1,117 active source records) after the first scheduled sync. |
| Render | **Deployed.** `internship-finder-api` (`srv-dastve60tbcc7392dfgg`): deploy `dep-db1c2oc9v7es73eshpd0` of `0a636e2` (Milestone 7.1) live (2026-10-04 21:14 UTC). Auto-deploy off, branch `main`. The only Render service. |
| Vercel | **Deployed** (production `dpl_AZuVPW533BkqzuzRwozvx12J5PEG`, `Ready`, aliased to `internship-finder-pi.vercel.app`; 2026-10-04 from a clean checkout of `0a636e2` via CLI). |
| Hosted acceptance | Verified with the owner's login on 2026-09-29 ([Production verification](#production-verification)); Milestone 4 hosted smoke on 2026-09-29 ([below](#milestone-4-hosted-smoke-2026-09-29)); Milestone 5 hosted smoke on 2026-10-01 ([below](#milestone-5-hosted-smoke-2026-10-01)); Milestone 6 release and smoke on 2026-10-02 ([below](#milestone-6-release-2026-10-02)); Milestone 7 release and ATS activation on 2026-10-04 ([below](#milestone-7-release-2026-10-04)). |
| Scheduled sync | **Active.** GitHub environment `production` (deployment branches: `main` only) with secret `PRODUCTION_DATABASE_URL` (Neon pooled URL); first dispatch green 2026-10-02. |

## Topology

```text
Browser ──HTTPS──► https://internship-finder-pi.vercel.app   (Vercel Hobby, project "internship-finder")
                     ├─ static Vite build (SPA fallback to index.html)
                     └─ /api, /api/* ──► https://internship-finder-api-eld4.onrender.com/api/*
                                          adds X-IF-Proxy-Secret (Production env only)
                                          (Render Free "internship-finder-api", Oregon, 1 instance, 1 worker)
                                               └─► Neon Free project sweet-dew-33937746, aws-us-west-2,
                                                   PostgreSQL 18, database internship_finder, direct endpoint
```

The only public app URL is the Vercel production alias. The browser never calls `onrender.com`. The Render URL answers directly, but only public endpoints work without a session, and direct login attempts share one throttle bucket.

## Cost Constraint

$0/month, no payment method, no automatic billing or upgrade ([ADR-009 §2](decisions/ADR-009-hosted-deployment-architecture.md#2-zero-cost-rule-permanent)). All three services are on free plans with no card: Vercel Hobby (owner-confirmed 2026-09-28), Render Free, Neon Free. If any platform asks for payment information, stop that path and write a new ADR.

## Configuration

### Render (`internship-finder-api`)

| Setting | Value |
|---|---|
| Plan / region / instances | Free / Oregon / 1 |
| Root directory | `backend` |
| Build | `pip install .` |
| Start | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (one worker; don't add `--workers`) |
| Health check | `/api/health` |
| Auto-deploy / PR previews | Off / off |

Environment variables (names only; values live in Render):

| Variable | Value |
|---|---|
| `DATABASE_URL` | Secret. Neon **direct** connection string (`neonctl connection-string`), as Neon prints it (`postgresql://…?sslmode=require…`); the app switches the driver |
| `SESSION_COOKIE_SECURE` | `true` |
| `SESSION_TTL_HOURS` | `24` |
| `PYTHON_VERSION` | `3.12` |
| `HOSTED` | `true` |
| `PROXY_SHARED_SECRET` | Secret. Random, ≥ 32 characters, identical to Vercel's |

Never set `INGESTION_FIXTURE_FILE`.

### Vercel (`internship-finder`, team `dude297s-projects`)

| Setting | Value |
|---|---|
| Plan | Hobby |
| Root directory / framework | `frontend` / Vite |
| Install / build / output | `npm ci` / `npm run build` / `dist` (also in `frontend/vercel.json`) |
| Node | 24.x |
| Git deployments | Disabled by `frontend/vercel.json` (`git.deploymentEnabled: false`); the project is connected to GitHub, but pushes and pull requests create no deployments |
| Deployment Protection | Standard (Vercel Authentication on everything except the production alias) |
| Production alias | `internship-finder-pi.vercel.app` |

Environment variables: **only** `PROXY_SHARED_SECRET`, type Sensitive, **Production** only. Nothing `VITE_*`, no API base URL, no database credentials. The `/api` route in `vercel.json` sends it as `X-IF-Proxy-Secret`, sets `Cache-Control: no-store`, and runs before the SPA fallback.

### Proxy secret

- Generate: `python -c "import secrets; print(secrets.token_urlsafe(48), end='')" > <file outside the repo>`.
- Set it from that file without displaying it: Render (API or dashboard) and `vercel env add PROXY_SHARED_SECRET production --sensitive --yes < <file>`. Delete the file afterwards.
- Rotate: set the new value in both places, redeploy Render, then redeploy Vercel production. Between the two steps (or with a mismatch) proxied logins fall back to the shared `direct` throttle bucket; nothing else breaks.

## Deploy Order

Always **migrate → Render → Vercel**, from a trusted local shell.

1. **Migrate** (only when the release adds migrations). In `backend/` with the venv active, set `DATABASE_URL` in this shell only and never echo it:
   ```powershell
   $env:DATABASE_URL = (neonctl connection-string --project-id sweet-dew-33937746 --database-name internship_finder --role-name internship_finder)
   alembic upgrade head
   alembic current     # expect the new head
   alembic check
   Remove-Item Env:DATABASE_URL
   ```
   Never run `alembic downgrade` against Neon. Offline `--sql` mode can't render `92a17353e5a8`; migrate online.
2. **Render:** push the reviewed commit to `main`, then **Manual Deploy → Deploy latest commit** (or `POST /v1/services/<id>/deploys`). Wait for `live`, then check `/api/health`.
3. **Vercel:** from a clean checkout of the same commit (`git worktree add --detach <dir> <sha>`), in the repository root: `npx vercel link --yes --project internship-finder --scope dude297s-projects`, then `npx vercel deploy --prod --yes`. Delete any `.env.local` the CLI creates. Verify the new deployment is aliased to `internship-finder-pi.vercel.app`.

### Owner bootstrap (done once)

With `DATABASE_URL` set as in step 1: `python -m app.cli create-owner --username <name>`. The password goes into `getpass` only. Password rotation: `set-password` (revokes all sessions).

### Unmerged branch validation

Milestone 3.5 was validated before merge by switching the Render service's branch to `feature/hosted-deployment-foundation` (auto-deploy stayed off) and deploying manually; Vercel production was deployed from a clean checkout of that branch. After the PR is merged: switch Render's branch back to `main`, deploy `main` on Render, and redeploy Vercel production from `main`. Done on 2026-09-29 for `d78b93d` (PR #7). The rebase merge rewrote the branch SHAs cited on this page: `36b9896` → `03e86c7`, `65964c6` → `17e5877`, `3563021` → `680c2b7`, `3ab655f` → `6eaaed6`.

Milestone 4 was released without the branch-swap step: PR #9 merged into `main` on 2026-09-29 (production `main` is `ca9b91b`). Release closeout: Neon migrated to `b41e7c9d2f60` (additive; existing boards backfilled scope `all`, pre-Milestone-4 evaluations kept NULL fit until the first Match Profile save), Render and Vercel production redeployed from `main`, then the hosted smoke below. The first Match Profile save on 2026-09-29 gave every pre-existing opportunity a fit score (1,055 evaluated in 6,359 ms).

The Vercel CLI's `vercel link` appends `.vercel` and `.env*` to the checkout's `.gitignore` and writes an `.env.local` (a short-lived OIDC token), so the deployment reports `gitDirty`. Both stay out of the build; delete `.env.local` and the checkout afterwards.

### Milestone 5 release (2026-10-01)

**Executed 2026-10-01** following the procedure below: [PR #11](https://github.com/dude297/internship-finder/pull/11) ([ADR-011](decisions/ADR-011-profile-source-ingestion-and-review.md)) rebase-merged at the approved head `12bb4cc`; resulting `main` `639e447`, post-merge CI green; Neon migrated `b41e7c9d2f60` → `c5a1e0f3d7b2`; Render deploy `dep-dautc2gjo6nc73ehekag`; Vercel production `dpl_8jfYs2Ychc77wiH7JbWCMjroEwUF`. Results: [Milestone 5 hosted smoke](#milestone-5-hosted-smoke-2026-10-01). The procedure is kept as the runbook for the next migrating release.

`c5a1e0f3d7b2` gives `profile_facts.review_state` a database default of `'accepted'` (kept after the migration, not dropped once applied). Milestone 4's Match Profile save creates `profile_facts` without naming `review_state`; manual facts are semantically accepted, and the default gives them exactly that value, so Milestone 4 code keeps working unmodified on the migrated schema. The CHECK `ck_profile_facts_review_state_matches_verified` (`extraction_method = 'manual' OR (review_state = 'accepted') = verified_by_user`) still rejects an unverified non-manual fact that omits `review_state` — only manual inserts benefit from the default. Consequence: there is no ordering hazard between the migration and the Render deploy, and a Render code rollback to the Milestone 4 release after the migration remains possible for existing Milestone 4 functionality (see [Rollback](#rollback)). Neon itself is still never downgraded. The Milestone 4 app simply ignores the new table and columns it doesn't know about; Milestone-5-only data (uploaded sources, imported facts) is invisible to it but untouched. Pending or rejected imported facts are unverified, so Milestone 4's fit filter (`verified_by_user OR manual`) ignores them as before; accepted imported facts are verified, so Milestone 4 would score them too, consistent with Milestone 5's behavior.

1. **Merge PR #11** (owner). Record the merged commit SHA.
2. **Verify post-merge CI** is green on `main` at that SHA.
3. **Migrate Neon** (same shell pattern as [Deploy Order](#deploy-order) step 1, existing `DATABASE_URL` pattern; never downgrade). Read-only baseline first, expected per the Milestone 4 smoke unless the owner used the app since:
   ```sql
   SELECT count(*) FROM opportunities;                                         -- 1,055
   SELECT count(*) FROM opportunity_source_records;                            -- 1,055
   SELECT count(*), count(fit_score) FROM opportunity_evaluations;             -- 4,220, 2,110
   SELECT count(*) FROM profile_facts;                                         -- 10
   SELECT count(*) FROM profile_sources;                                       -- 0
   SELECT pg_size_pretty(pg_database_size(current_database()));                -- ~18 MB
   SELECT version_num FROM alembic_version;                                    -- b41e7c9d2f60
   ```
   Stop if these drift without an explanation. Then `alembic upgrade head`, `alembic current` → `c5a1e0f3d7b2`, `alembic check`, remove `DATABASE_URL`.
4. **Verify the migration**, read-only:
   ```sql
   SELECT review_state, count(*) FROM profile_facts GROUP BY 1;                -- accepted: 10
   SELECT count(*) FROM profile_facts
    WHERE extraction_method <> 'manual' AND (review_state = 'accepted') <> verified_by_user;  -- 0
   SELECT count(*) FROM opportunity_evaluations;                               -- unchanged (4,220)
   SELECT count(*) FROM profile_source_artifacts;                              -- 0
   SELECT column_default FROM information_schema.columns
    WHERE table_name = 'profile_facts' AND column_name = 'review_state';       -- 'accepted'::text (or equivalent)
   ```
   Stop (and don't deploy) if `alembic current` or `alembic check` disagree. The Milestone 4 app keeps running correctly against the migrated schema in the meantime, so there's no rush to deploy Render.
5. **Render:** deploy the merged SHA on `internship-finder-api` (`srv-dastve60tbcc7392dfgg`, never the stray `internship-finder`) — Manual Deploy, or the deploys API with the key from the local Render CLI config, never printed.
6. **Verify:** wait for `live`; `/api/health` `200`; confirm the deploy's commit SHA; a synthetic wrong login → `401` (database reachable).
7. **Vercel:** clean detached worktree at the merged SHA, `vercel link`, `vercel deploy --prod`, delete `.env.local` and the worktree, verify the alias (as for Milestone 4).
8. **Hosted smoke** through the Vercel URL, logged in as the owner (browser, or a script whose session cookie is supplied locally and never logged). Synthetic, fabricated documents only:
   - upload a synthetic text résumé with a unique marker line → pending facts; evaluation count unchanged (no pass on upload)
   - accept one skill → `catalog_pass: true`; record the time and `evaluated_opportunities`
   - reject one fact; re-parse → no duplicates, decided facts unchanged
   - download → identical bytes; `attachment`, `nosniff`, `no-store`
   - upload a synthetic text PDF (`tests/resume_fixtures.make_text_pdf`) → `201`; record latency (child-process start on Render)
   - same file again → `409`; a > 2 MB file → `413`
   - optional, owner's call: while the flate-bomb fixture parses (up to 15 s), `/api/health` answers and a second PDF gets `503` with `Retry-After`
   - delete both synthetic sources → `catalog_pass: true` (an accepted fit fact existed)
9. **Final counts and reconciliation:** `profile_sources` 0, `profile_source_artifacts` 0, `profile_facts` 10 (all accepted), migration `c5a1e0f3d7b2`, database size. Evaluations: 4,220 + the accept pass + the delete pass, each at most 1,055 (only opportunities whose fit input changed get a row), so at most 6,330; record the actual `evaluated_opportunities` of both passes and reconcile exactly. Record everything in [PROJECT_STATE.md](../PROJECT_STATE.md) and the Production Verification table.
10. **Release-state docs PR**, if needed, to record the above once production reflects it.

### Milestone 6 release (2026-10-02)

[PR #13](https://github.com/dude297/internship-finder/pull/13) ([ADR-012](decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)) rebase-merged at the approved head `ff47970` (CI `37064233989`); resulting `main` `80257c5`, post-merge CI `37066645594` green (backend, frontend, e2e). All counts below are aggregates from read-only queries.

| Step | Result |
|---|---|
| Pre-migration baseline | `c5a1e0f3d7b2`; 1,055 opportunities and source records (all active); 0 canonical requirements; 6,330 evaluations (4,220 with fit, 1,055 latest, all `needs_verification`); 6,330 rule results; 1,055 `unassessed`; 1 profile, 10 facts, 0 profile sources/artifacts; 1 ingestion source, 2 runs; 1 owner; 23 MB |
| Migration | `e6d1a4b8c2f9`, `alembic check` clean. `opportunity_requirement_candidates` exists; `opportunities.requirements_stale_since` and `requirement_extraction_fingerprint` exist; the kind CHECK accepts `ashby`. Every count identical to the baseline (0 candidates, 0 fingerprints, no evaluation, no status change) |
| Milestone 5 code on the new schema | `/api/health` `200`; dummy-cookie session lookup `200` unauthenticated; private APIs `401` |
| Render | `dep-db03iknavr4c73e10b8g` of `80257c5`, `live`; Free, Oregon, 1 instance, one worker, auto-deploy off, branch `main`, env var names unchanged. `/api/health` `200`; `/docs`, `/openapi.json` `404`; requirement-review and needs-review routes `401` (unknown routes `404`); synthetic wrong login `401`; clean startup log |
| Vercel | `dpl_8kqCpb15vP5q1rcJpsSB3Pvt6XJk`, `Ready`, aliased. `/api/health` `200` JSON; `/login`, `/opportunities`, `/sources`, unknown SPA path → `index.html`; `/api/nope`, `/api/health/` → JSON `404`. Bundle contains the Requirement Review panel, the `needs_review` filter, deadline filters and badges, Source Health labels, and the Ashby option; no Render hostname. Temporary checkout and `.env.local` deleted |
| Hosted smoke (owner login via `getpass`, session in memory, logged out) | Authenticated session, list (1,055), Match Profile, sources: `200`. One fabricated opportunity (`ZZZ M6 RELEASE SMOKE — Synthetic Robotics Internship`, `Synthetic Example Org`): 3 pending `requirements-rules` suggestions with excerpts (minimum age, education, citizenship); pending changed nothing (`unassessed`, no requirements, same evaluation). One batch (accept age, edit + accept education, reject citizenship): 2 canonical `deterministic_parser` requirements, edit applied, `partial`, one evaluation. Editing the accepted age suggestion: relinked to a new row, no duplicate, old row removed. Explicit `complete` applied. 26/26 PASS |
| Smoke cleanup | Guards verified (exact UUID, title prefix, organization, manually curated, manual source), then the app's `DELETE /api/opportunities/{id}` (`204`, then `404`). Read-only check: 0 rows left for that UUID or title in opportunities, candidates, requirements, evaluations, source records, identifiers, applications; 0 orphaned rule results; every production count identical to before the smoke |
| Read-only discovery checks | `requirement_review` `needs_review`/`pending`/`stale`, `deadline_within` 7/14/30, `has_deadline`, `sort=deadline`: all `200`. The feed has no deadlines, so the deadline filters matched only the smoke opportunity while it existed |
| GitHub environment | `production` (created earlier by the Vercel GitHub integration as `Production`; names are case-insensitive) restricted to branch `main` (custom policy, verified) before adding `PRODUCTION_DATABASE_URL` (Neon pooled URL, checked read-only with the app engine first). Secret name verified via metadata only; no repository secrets |
| First sync ([run 37077086322](https://github.com/dude297/internship-finder/actions/runs/37077086322), manual dispatch on `main`) | Green in 3 m 17 s; schema check passed; log shows counts only (`DATABASE_URL: ***`). Feed: 1,117 fetched, 138 created, 102 updated (includes the one-time type reclassification: `other` 93 → 2), 877 unchanged, 76 closed, 0 invalid, 0 errors. All 76 closed postings verified absent from the live feed; active records equal the feed's 1,117 IDs exactly. Source Health `stale` → `healthy` |
| Requirement scan (`python -m app.cli scan-requirements`, once) | 1,193 scanned, 1,050 refreshed, 143 unchanged, 0 failed, **0 suggestions**, 92.9 s. Cause: no production opportunity has a description (the feed has no description field). Unchanged by the scan, verified with per-opportunity digests: latest eligibility, assessment status and staleness, canonical requirement IDs, newest evaluation. Fingerprints 143 → 1,193 (all valid) |
| Final counts | `e6d1a4b8c2f9`; 1,193 opportunities and source records (1,117 active); 0 canonical requirements; 0 candidates; 6,492 evaluations (4,382 with fit, 1,193 latest, all `needs_verification`); 1,193 `unassessed`; 1 ingestion source (`healthy`), 3 runs; 1 profile, 10 facts, 0 profile sources/artifacts; 1 owner; 26 MB. The 162 evaluations since the baseline come from the sync (138 new postings + 24 updated ones whose eligibility inputs changed) |
| Security | Actions sync log, Render logs since the deploy (522 lines), and command output: no database URL, password, cookie, CSRF or session token, or profile data. These docs contain no secret values |

Not done by design: no Ashby source in production (sources can't be deleted; Ashby is covered by CI and integration tests); no real opportunity's suggestions accepted or rejected. Rollback: as for Milestone 5, a Render/Vercel code rollback to `639e447` stays possible while no Ashby source exists ([data-model.md](data-model.md)); Neon is never downgraded.

### Milestone 7 release (2026-10-04)

| Step | Result |
|---|---|
| Merge | [PR #17](https://github.com/dude297/internship-finder/pull/17) rebase-merged at the approved head `64ce84d` (CI `37188071021`); `main` `bc23629`; post-merge CI `37191644826` green (backend, frontend, e2e). No migration (Neon stays `e6d1a4b8c2f9`) |
| Scheduled sync on Milestone 7 code (before deploy) | [Run 37221123774](https://github.com/dude297/internship-finder/actions/runs/37221123774): feed 1,107 fetched, 59 updated (the expected one-time Ashby cross-source identifier), 7 closed, 0 invalid, 0 errors |
| Render | `dep-db1bksjncjis73c2apr0` of `bc23629`, `live` 2026-10-04 20:45 UTC; Free, Oregon, 1 instance, one worker, auto-deploy off, branch `main`, env var names unchanged. `/api/health` `200`; `/docs`, `/openapi.json` `404`; `/api/sources/discovery` `401` (route present); synthetic wrong login `401` |
| Vercel | `dpl_Gj9D5tdBYQENGrMavySfoa3xFS57`, `Ready`, aliased to `internship-finder-pi.vercel.app`, from a clean detached checkout of `bc23629` (`.env.local` deleted). `/api/health` `200`, `/api/nope` `404`, `/login` and `/sources` `200`; `/api/*` `Cache-Control: no-store`, `X-Frame-Options: DENY`; bundle contains Source Coverage / Suggested Sources / Add selected, no Render hostname |
| Coverage baseline (`source-coverage`, read-only) | 1,107 open; 0 with a description (**0.0%**); 0 ATS-backed; 1,107 feed-only; 288 enrichable; 819 unsupported (Workday 595, Oracle 147, SmartRecruiters 40, other 13, Rippling 11, Workable 8). 163 suggestions (Greenhouse 106, Lever 16, Ashby 41). 1,202 opportunities, 0 curated, 0 canonical requirements, 0 candidates, 6,501 evaluations, all latest `needs_verification`, all `unassessed`; 26 MB |
| Activation | 20 boards added through the trusted discovery service (`add_from_discovery`, the code path behind `POST /api/sources/discovery/add`; never raw inserts), all **Internships only**, ranked by feed-only coverage with exact identities; `testnisc` skipped (looks like a test board). Each synced manually with `python -m app.cli sync-source` |
| Batch 1 (10) | Greenhouse `morsecorpcoop`, `akunacapital`, `hpiq`, `coinbase`, `robinhood`, `verkada`, `waymo`; Lever `hermeus` (global); Ashby `bedrock-robotics`, `ramp`. All `success`: 1,447 fetched, 128 created, **53 deduplicated** (exactly the 53 predicted), 0 updated/closed/invalid/errors; 9.0–53.6 s each |
| Batch 2 (10) | Greenhouse `devtechnology`, `dvtrading`, `lyft`, `singlestore`, `thenuclearcompany`, `advancedspace`; Ashby `allen-control-systems`, `base-power`, `reflect-orbital`; Lever `kitware` (global). All `success`: 706 fetched, 78 created, **35 deduplicated** (exactly as predicted), 0 updated/closed/invalid/errors |
| Integrity (read-only) | 88 opportunities now hold a feed record and an ATS record, all 88 with the ATS description; 0 opportunities with two active ATS records; 0 run errors / identity conflicts; all 206 new opportunities typed `internship` with intern/co-op titles; curated digest unchanged (0 curated). Same-title-and-organization groups: 71 (66 pre-existing in the feed; the 5 new ones are distinct ATS postings with different job IDs, never a feed-only row beside a matching ATS row) |
| Requirements | 4 `pending` candidates (all `education`) on 4 opportunities; **0 accepted, 0 rejected, 0 canonical requirements**; every latest evaluation still `needs_verification`, every opportunity `unassessed`, 0 stale. Nothing was reviewed |
| Coverage after | 1,313 open; **294 with a description (22.4%)**; 294 ATS-backed; 1,019 feed-only; 200 enrichable; 819 unsupported. 1,408 opportunities, 1,496 source records, 6,795 evaluations (+294: 206 new + 88 updated); 29 MB |
| Scheduled sync check ([run 37234279820](https://github.com/dude297/internship-finder/actions/runs/37234279820), manual dispatch) | Green; 20 ATS sources first, the feed last; 21 run, 0 failed, 0 skipped; sync **24.6 s**, workflow 50 s (limit 20 min). Most boards answered `no_change`/unchanged |
| Security | Command output and logs show counts only; no database URL, key, cookie, or token printed. These docs contain no secret values |

Stopped at 20 sources: the next suggestions cover about 3 feed postings each. Rollback: disable a source (see [operations.md](operations.md#milestone-7-production-activation-runbook-executed-2026-10-04)); a code rollback to `80257c5` is possible (no migration), but Milestone 6 code doesn't apply ATS authority, so disable the ATS sources first.

### Milestone 7.1 release (2026-10-04)

| Step | Result |
|---|---|
| Merge | [PR #19](https://github.com/dude297/internship-finder/pull/19) rebase-merged at head `d24b836` (rebased onto the Milestone 7 docs; code identical to the reviewed `52c9e55`); `main` `0a636e2`; post-merge CI `37234964868` green |
| Migration | Neon `e6d1a4b8c2f9` → `f2a7c9d4e1b3`, `alembic current` at head, `alembic check` clean. Every other baseline value identical before/after (1,409 opportunities, 6,796 evaluations, 4 pending candidates, 0 canonical requirements, 29 MB) |
| Render | `dep-db1c2oc9v7es73eshpd0` of `0a636e2`, `live` 2026-10-04 21:14 UTC; settings unchanged. `/api/health` `200`, `/docs` `404`, `/api/opportunities?opportunity_type=…` `401` unauthenticated, synthetic wrong login `401` |
| Vercel | `dpl_AZuVPW533BkqzuzRwozvx12J5PEG`, `Ready`, aliased, from a clean checkout of `0a636e2` (`.env.local` deleted). `/api/health`, `/opportunities`, `/login` `200`; bundle contains the Volunteer label and the Type filter, no Render hostname |
| Synthetic smoke (app service layer against Neon: the functions the API routes call, no raw SQL writes) | `ZZZ M7.1 RELEASE SMOKE — Synthetic STEM Tutor Volunteer …`, `Synthetic Example Org`, minimum age 16, deadline 2999-01-01: created as `volunteer` and manually curated; Type filter `volunteer` finds it, `internship` excludes it; `has_deadline` finds it; evaluated on create (`needs_verification`, `ELIG-AGE-001` ran); application tracked as `saved`; edited to `other` and back. 13/13 PASS |
| Cleanup | Exact UUID + title + organization + curated guards, then the same delete as `DELETE /api/opportunities/{id}`. 0 rows left in opportunities, evaluations, requirements, source records, applications; 0 volunteer opportunities; opportunity and evaluation counts identical to before the smoke |
| Not done by design | No automated volunteer source (research only: [volunteer-sources-2027.md](research/volunteer-sources-2027.md)) |

## Rollback

- **Code (Render):** Render dashboard → Deploys → **Rollback** to an earlier deploy, or deploy an earlier commit. Health check afterwards. After the `c5a1e0f3d7b2` migration, a code rollback to the Milestone 4 release is possible: the `review_state` default keeps Milestone 4's Match Profile save working on the migrated schema, so this is a normal rollback, not a schema/code coupling to avoid.
- **Frontend (Vercel):** `npx vercel rollback` (or promote an earlier production deployment in the dashboard). Hobby supports rolling back to the previous production deployment.
- **Schema:** forward only: write a new migration. Don't downgrade Neon.
- **Data:** Neon Free keeps a short restore history (point-in-time restore / branch from a past point within the free window). For anything older there's no backup yet (see [operations.md](operations.md#database-backup-considerations-planned)).
- **Secrets:** rotate `PROXY_SHARED_SECRET` as above; rotate the Neon role password in Neon, then update Render's `DATABASE_URL` and redeploy.
- **Milestone 5 specifically:** if Render/Vercel are rolled back to the Milestone 4 release after the `c5a1e0f3d7b2` migration, Milestone 5 data (`profile_sources`, `profile_source_artifacts`, non-manual `profile_facts`) stays in the database, unused and untouched by the Milestone 4 app, until a forward roll re-deploys Milestone 5 code.

## Production Verification

Run after every deploy. Results of the first hosted validation (2026-09-28) are recorded.

| Check | How | Result 2026-09-28 |
|---|---|---|
| Health through Vercel | `GET https://internship-finder-pi.vercel.app/api/health` | `200 {"status":"ok"}` |
| Database reachable from Render | A synthetic wrong login → `401` (not `500`) | `401` |
| Unknown API path | `GET /api/nope`, `GET /api` | FastAPI JSON `404`, not `index.html` |
| No slash redirect | `GET /api/health/` | `404`, no `Location` header |
| SPA deep links | `GET /login`, `/sources`, `/opportunities/123` | `200` `index.html` |
| API docs hidden | `/docs`, `/redoc`, `/openapi.json` on Render; `/api/docs` via Vercel | `404` on Render; via Vercel `/docs` etc. are the SPA shell, not API docs |
| API caching | `Cache-Control` on `/api/*` | `no-store` (also on `401`/`404`) |
| Static assets | `Cache-Control` on `/assets/*.js` | Vercel default (`public, max-age=0, must-revalidate`, edge-cached, revalidated by ETag) |
| Security headers | All responses | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` |
| Direct Render throttle | 11 wrong logins to the Render URL, each with a different forged `X-Forwarded-For` and a wrong `X-IF-Proxy-Secret` | `401` ×10, then `429`: one shared `direct` bucket |
| Proxy secret matches | While the direct bucket is full, one wrong login through Vercel | `401` (not `429`): proxied requests use their own bucket, so Render accepted the secret |
| Non-production URLs | Deployment URLs and `internship-finder-dude297s-projects.vercel.app` | `302` to Vercel SSO |
| Git pushes don't deploy | Push of the feature branch | No Vercel deployment created |
| Cold start | First request after idle | See [Cold starts](#cold-starts) |
| Session cookie (login through Vercel) | `Set-Cookie` attributes | `if_session`: `HttpOnly; Secure; SameSite=lax; Path=/; Max-Age=86400`, no `Domain` (host-only on the Vercel host) |
| CSRF | Unsafe private request without / with a wrong / with the valid `X-CSRF-Token` | `403` / `403` / `200` |
| First discovery sync (through Vercel) | Sources → Sync now | `success` in 30.8 s: 1,055 fetched, 1,055 created; 0 updated, deduplicated, unchanged, closed, invalid, errors. Finished inside the proxy window |
| Second sync | Same | `no_change` (HTTP 304) in 0.8 s |
| Profile re-evaluation (synthetic profile, 1,055 opportunities) | Save profile / change date of birth / save unchanged | 9.7 s / 9.0 s / 0.35 s (1,055 / 1,055 / 0 re-evaluated) |
| Invalid source links | `localhost`, `127.0.0.1`, `169.254.169.254`, `file://`, unknown host | `422` before any fetch |
| Credential-bearing / custom-port board links | `https://user:pw@boards.greenhouse.io/x`, `https://jobs.lever.co:8443/x` | Accepted (`201`) by `3ab655f`; only the board name was kept and nothing was fetched from them. Fixed in `65964c6` (now `422`, deployed). The two probe sources were deleted |
| Proxied throttle through Vercel | 11 wrong logins, each with different forged `X-Forwarded-For` and `X-Vercel-Forwarded-For` | Before `36b9896`: all `401` (forgeable key, see below). After: `401` ×10, then `429`; the direct bucket stays separate; existing sessions unaffected |
| Database after the first sync | Aggregate queries only | 13 MB; 1,055 opportunities, 1,055 source records, 2,110 evaluations, 2 runs |
| Session after a cold start | Idle > 15 min, then a session check through Vercel | Render restarted; `200` after 73 s; still authenticated as the owner |
| Session survives a Render redeploy | Session check after deploying `3563021` and `36b9896` | Still authenticated as the owner; catalog intact (1,055) |
| Board-link fix live | The credential and port links above, after deploying `3563021` | `422` |
| **Not run:** one Greenhouse/Lever board | | Optional; no board chosen (adding one imports all its postings, and sources can't be deleted) |

**Fixed: forgeable per-client throttle key.** On 2026-09-29, 11 wrong logins through Vercel with different forged `X-Forwarded-For` values all got `401`. A temporary diagnostic build (logging only, from a throwaway branch, removed right after) showed what Render receives: `X-Forwarded-For` is `<client>, <Vercel egress>, <Cloudflare>, <Render internal>`, and `X-Vercel-Forwarded-For` is `<client>`, but in some requests the `<client>` value in either header was the one the caller sent. No forwarded header is trustworthy, so all proxied logins now share one `proxy` bucket (`36b9896`, [ADR-009 §6 amendment](decisions/ADR-009-hosted-deployment-architecture.md#6-login-rate-limiting-behind-the-proxy)). Trade-off: 10 failed attempts by anyone through the site block new logins for 15 minutes; existing sessions keep working.

Global failed-login cap (50 per 15 minutes) is covered by unit tests only: a hosted test needs five distinct client addresses, since a blocked key stops adding failures.

### Milestone 4 hosted smoke (2026-09-29)

Run by the owner against production after the release (Neon migrated to `b41e7c9d2f60`, Render and Vercel redeployed from `main` at `ca9b91b`). All PASS.

| Check | Result |
|---|---|
| Match Profile `GET` | PASS |
| First Match Profile save | evaluated 1,055 / unchanged 0 in 6,359 ms |
| Identical save (no changes) | evaluated 0 / unchanged 1,055 in 1,995 ms |
| Changed save | evaluated 1,055 / unchanged 0 in 6,391 ms |
| Recommended list page (100) | 306 ms |
| Recommended list page (50) | 216 ms |
| Full catalog load | all 1,055 opportunities loaded |
| Eligibility-first / fit ordering | PASS |
| Scoring coverage | all 1,055 scored with scoring version `v1`; coverage present (values `[100]`) |
| "Why This Match" breakdown | full breakdown PASS |
| Board scope | built-in source remains scope `all` |
| Run counts | latest ingestion run exposes `filtered_count` |

Final Neon counts (read-only, 2026-09-30): 1,055 opportunities; 1,055 source records; 4,220 evaluations (2,110 with fit); 1,055 current evaluations, all with fit score and scoring version `v1`; 1 ingestion source; 2 ingestion runs (both 2026-09-29 00:37 UTC, before the smoke); 1 profile; 0 profile sources; 10 profile facts; 1 owner account; 18 MB database size. All 1,055 current evaluations are `needs_verification` (imported requirements are unassessed), fit range 2–22; cross-bucket dominance is covered by deterministic backend/E2E tests, not by this production data. The hosted Match Profile used for the smoke is still the synthetic one; it is left in place deliberately (clearing it would add another 1,055 evaluation rows) until the owner replaces it with the real Match Profile through the app.

Cleanup (done 2026-10-01): the stray Render web service `internship-finder` (`srv-dasrvgt9fdbs73eqlmi0`, Free) was deleted after verifying it wasn't `internship-finder-api`, every deploy had `build_failed` (never live), auto-deploy was off, and its URL served nothing. `internship-finder-api` stayed healthy afterwards.

### Milestone 5 hosted smoke (2026-10-01)

Run through the Vercel URL as the owner (password via `getpass`; the session held in memory only and logged out at the end) with **fabricated** files only: a 237-byte text résumé and small text PDFs. No real résumé, and no hostile PDF against production (the flate bomb is covered by Linux CI/container tests). All PASS.

| Check | Result |
|---|---|
| Pre-migration baseline (read-only) | `b41e7c9d2f60`; 1,055 opportunities and source records; 4,220 evaluations (2,110 with fit); 0 profile sources; 10 facts; 1 profile; 1 owner; 18 MB |
| Migration | `c5a1e0f3d7b2`, `alembic check` clean; `profile_source_artifacts` exists; `profile_sources` has `content_type`, `byte_size`, `parser_name`, `parser_version`; `review_state` NOT NULL, default `'accepted'`; `ck_profile_facts_fact_review_state` and `ck_profile_facts_review_state_matches_verified` present; 10/10 facts `accepted`; 0 sources/artifacts; 4,220 evaluations (no rescore) |
| Milestone 4 app on migrated schema | `/api/health` `200`, dummy-cookie session lookup `200` unauthenticated, profile API `401` |
| Render direct after deploy | `/api/health` `200`; `/docs`, `/openapi.json` `404`; dummy-cookie session `200` unauthenticated; `/api/profile/sources` `401` (was `404` on Milestone 4); clean startup log |
| Vercel routing | `/api/health` `200` JSON; `/login`, `/profile/sources`, `/opportunities`, unknown SPA path → `index.html`; `/api/nope` and `/api/health/` → JSON `404`, no `Location`; no Render hostname in responses or bundle; bundle contains the Imported Profile UI |
| Source list before smoke | empty |
| Text upload | `201`; parser `resume-sections` v1; 4 pending facts (skill, course, project, activity; candidates already accepted in the Match Profile were skipped by design); duplicate → `409` |
| Download | byte-identical; `attachment`, `nosniff`, `no-store` |
| Review batch (accept 1 skill with an edited name, 1 course, 1 project; reject 1 activity) | `200`; exactly one catalog pass, 1,055 evaluated; accepted 3, rejected 1; edit applied |
| Persistence | Separate second login: same review state |
| Re-parse | `200`; no duplicates; decided facts kept; rejected fact not resurrected; the edited skill's original name returned as one new pending fact (see [PROJECT_STATE.md](../PROJECT_STATE.md) limitations) |
| PDF upload | `201`; 3 pending facts; `/api/health` `200` right after |
| > 2 MB upload | `413` |
| Two different benign PDFs at once | `201` + `503` with `Retry-After: 5` (one extraction child per process) |
| Delete text source | `200`; one catalog pass, 1,055 evaluated (accepted fit facts removed) |
| Delete PDF sources | `200`; no catalog pass (pending facts only) |
| After deletes | source and download `404`; source list empty; Match Profile identical to before (response digest) |

Evaluation arithmetic: 4,220 before the smoke + 1,055 (accept) + 1,055 (delete) = **6,330** after; history is append-only by design. Final counts (read-only): 0 profile sources, 0 artifacts, 10 profile facts (all manual, `accepted`), 1,055 latest evaluations all with fit and scoring version `v1`, 4,220 evaluations with fit, 23 MB. The hosted Match Profile is still the synthetic one, left in place for the owner to replace through the app.

PDF safety in production: Render runs 1 instance and 1 uvicorn worker; extraction runs in a spawned child with a 15 s time limit and a 256 MB address-space limit (Linux), and at most one child per process (a second concurrent PDF gets `503`, `Retry-After: 5`).

## Cold Starts

Render Free sleeps after about 15 minutes without traffic. Observed 2026-09-28: the first proxied request arrived about 07:25 UTC, Render started the process at 07:27:46, and uvicorn was ready at 07:28:10, so the wake took **about 3 minutes**. Meanwhile Vercel answered `502` (`text/plain`, `ROUTER_EXTERNAL_TARGET_ERROR`). A second test on 2026-09-29 (Render slept at 00:53:48 UTC, request at about 01:09:33): the process started at 01:10:28 and was ready at 01:10:44. Vercel held that first request and returned `200` after **73 s**, and the existing session was still authenticated (sessions are database rows, so they survive restarts). Wake time varies from about 1 to 3 minutes. The frontend treats any non-`401` failure of the session check (network error, 5xx, non-JSON) as "server waking up", retries automatically (backoff over about a minute, each attempt also waiting on Vercel's upstream timeout), then offers **Retry**. It never treats it as a logout. No keep-alive pings, by design.

## Scheduling

Since the Milestone 6 release (2026-10-02): the GitHub Actions workflow `.github/workflows/sync-production.yml` (twice daily, 06:17 and 18:17 America/Los_Angeles, plus `workflow_dispatch`). It reads `PRODUCTION_DATABASE_URL` from the GitHub `production` **environment** secret, runs only on `main` of this repository, and never runs for pull requests or pushes ([ADR-009 amendment](decisions/ADR-009-hosted-deployment-architecture.md#amendment-2026-10-01-scheduled-source-sync-milestone-6)). Configured 2026-10-02: deployment branches restricted to `main` (custom branch policy) before the secret was added; the secret is the Neon pooled URL, piped from `neonctl connection-string --pooled` into `gh secret set PRODUCTION_DATABASE_URL --env production` (stdin, never displayed). Without the secret, every run fails fast without touching anything. No Render or Vercel cron, and no keep-alive or uptime pings.

Configuring the secret (a release step for the owner only; never in a file, a command-line argument, or chat): GitHub → Settings → Environments → **New environment** `production` → **Deployment branches: Selected branches → `main`** (required: otherwise a workflow on another branch could name the environment and read the secret; adding yourself as a required reviewer is optional) → **Add environment secret** `PRODUCTION_DATABASE_URL` with the Neon pooled `postgresql+psycopg://…?sslmode=require` URL. Or run `gh secret set PRODUCTION_DATABASE_URL --env production` and paste the value at its prompt.

## Free-Tier Behavior

- **Render Free:** sleeps when idle (cold starts above); monthly instance hours are capped. Exhaustion suspends the service, never bills.
- **Neon Free:** compute auto-suspends when idle (the first query after that is slower; `pool_pre_ping` reconnects); storage is capped (the empty schema is 8.4 MB). Exhaustion suspends compute or blocks writes, never bills.
- **Vercel Hobby:** usage limits pause or limit the project, never bill.
- Long requests: the first discovery sync (30.8 s hosted), profile re-evaluation over the whole catalog (~10 s for 1,055 opportunities hosted), and a Match Profile save that scores the whole catalog (6.4 s for 1,055 opportunities hosted, measured 2026-09-29) run inside one proxied request. None hit Vercel's external-rewrite timeout. If one ever is cut off, the backend may still finish and commit: refresh before retrying (a second sync of the same source reports "already syncing" until the first ends).

## Maintenance

Update this file whenever the production process changes. Never add secret values.
